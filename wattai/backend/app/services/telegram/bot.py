"""
Telegram Bot
- Receives unknown_appliance events from Redis.
- Asks user: "New 2.2 kW load detected. What is this appliance?"
- Saves confirmed name → ApplianceProfile.
- Handles commands: /status /bill /tips /alerts
"""
import asyncio
import json
import logging
from decimal import Decimal

import redis.asyncio as aioredis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.db.models import ApplianceProfile, SpikeEvent, User, Device, Reading, Tenant

logger = logging.getLogger(__name__)
TELEGRAM_NOTIFY_CHANNEL = "telegram_notify"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_user_by_chat_id(session: AsyncSession, chat_id: str) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_chat_id == str(chat_id))
    )
    return result.scalar_one_or_none()


async def get_latest_reading(session: AsyncSession, tenant_id: str) -> Reading | None:
    result = await session.execute(
        select(Reading)
        .join(Device, Device.id == Reading.device_id)
        .where(Device.tenant_id == tenant_id)
        .order_by(Reading.time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to WattAI!\n\n"
        "Commands:\n"
        "/status — live power reading\n"
        "/bill — this month's estimated bill\n"
        "/tips — energy-saving tips\n"
        "/alerts on|off — toggle spike alerts\n"
        "\nLink your account at app.yourdomain.com → Settings → Telegram."
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    engine = ctx.bot_data["engine"]
    chat_id = str(update.effective_chat.id)

    async with AsyncSession(engine) as session:
        user = await get_user_by_chat_id(session, chat_id)
        if not user:
            await update.message.reply_text("Account not linked. Visit app.yourdomain.com → Settings.")
            return

        reading = await get_latest_reading(session, user.tenant_id)
        if not reading:
            await update.message.reply_text("No readings yet. Check your meter is provisioned.")
            return

        await update.message.reply_text(
            f"Live reading ({reading.time.strftime('%H:%M')})\n"
            f"Power:   {reading.active_power} kW\n"
            f"Voltage: {reading.voltage} V\n"
            f"Current: {reading.current_a} A\n"
            f"PF:      {reading.power_factor}\n"
            f"Freq:    {reading.frequency} Hz\n"
            f"Energy:  {reading.forward_energy} kWh"
        )


async def cmd_bill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    engine = ctx.bot_data["engine"]
    chat_id = str(update.effective_chat.id)

    async with AsyncSession(engine) as session:
        user = await get_user_by_chat_id(session, chat_id)
        if not user:
            await update.message.reply_text("Account not linked.")
            return

        # Fetch tenant for currency
        tenant = await session.get(Tenant, user.tenant_id)

        # Simple: sum forward_energy delta this month (Premium: add tariff tiers)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        result = await session.execute(
            select(Reading)
            .join(Device, Device.id == Reading.device_id)
            .where(
                Device.tenant_id == user.tenant_id,
                Reading.time >= month_start,
            )
            .order_by(Reading.time.asc())
        )
        readings = result.scalars().all()

        if len(readings) < 2:
            await update.message.reply_text("Not enough data yet for a bill estimate.")
            return

        total_kwh = float(readings[-1].forward_energy or 0) - float(readings[0].forward_energy or 0)
        currency = tenant.currency or "USD"
        # Use first tariff rule as flat rate if no block/TOU logic here
        rate = 0.10  # fallback cents
        estimated = total_kwh * rate

        await update.message.reply_text(
            f"Month-to-date estimate\n"
            f"Usage: {total_kwh:.2f} kWh\n"
            f"Est. cost: {currency} {estimated:.2f}\n\n"
            "Upgrade to Premium for block-tariff and TOU-aware billing."
        )


async def cmd_tips(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Energy tips for today:\n\n"
        "- Run heavy appliances (washer, AC) before 08:00 or after 22:00.\n"
        "- Your AC is your top consumer — raise the setpoint by 1°C to save ~6%.\n"
        "- Enable Premium AI for personalised load-shifting recommendations."
    )


# ---------------------------------------------------------------------------
# Appliance confirmation dialog
# ---------------------------------------------------------------------------

async def handle_unknown_appliance(bot, engine, event: dict):
    """Send Telegram message asking user to name the new appliance."""
    tenant_id = event["tenant_id"]
    spike_id = event["spike_id"]
    delta_kw = event["delta_kw"]

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.telegram_chat_id.isnot(None),
                User.role.in_(["owner", "admin"]),
            )
        )
        users = result.scalars().all()

    for user in users:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("AC / HVAC", callback_data=f"name:{spike_id}:AC / HVAC"),
                InlineKeyboardButton("Washing machine", callback_data=f"name:{spike_id}:Washing machine"),
            ],
            [
                InlineKeyboardButton("Water heater", callback_data=f"name:{spike_id}:Water heater"),
                InlineKeyboardButton("Other (type name)", callback_data=f"name:{spike_id}:__type__"),
            ],
            [
                InlineKeyboardButton("Ignore", callback_data=f"name:{spike_id}:__ignore__"),
            ],
        ])
        try:
            await bot.send_message(
                chat_id=user.telegram_chat_id,
                text=(
                    f"New {delta_kw} kW load detected on your meter.\n"
                    f"What is this appliance?"
                ),
                reply_markup=keyboard,
            )
        except Exception as exc:
            logger.warning(f"Could not notify {user.telegram_chat_id}: {exc}")


async def callback_appliance_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # "name:{spike_id}:{name}"
    parts = data.split(":", 2)
    if len(parts) < 3:
        return

    _, spike_id, name = parts
    engine = ctx.bot_data["engine"]

    if name == "__ignore__":
        await query.edit_message_text("Spike ignored.")
        return

    if name == "__type__":
        # Ask user to type the name
        ctx.user_data["pending_spike_id"] = spike_id
        await query.edit_message_text("Please type the appliance name:")
        return

    await save_appliance(engine, spike_id, name, update.effective_chat.id)
    await query.edit_message_text(f"Saved as '{name}'. Will auto-recognise this load in future.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Catch free-text appliance names typed after 'Other'."""
    pending = ctx.user_data.get("pending_spike_id")
    if not pending:
        return

    name = update.message.text.strip()
    engine = ctx.bot_data["engine"]
    await save_appliance(engine, pending, name, update.effective_chat.id)
    ctx.user_data.pop("pending_spike_id", None)
    await update.message.reply_text(f"Saved as '{name}'. Auto-recognition active.")


async def save_appliance(engine, spike_id: str, name: str, chat_id):
    async with AsyncSession(engine) as session:
        spike = await session.get(SpikeEvent, spike_id)
        if not spike:
            return

        device = await session.get(Device, spike.device_id)
        if not device:
            return

        profile = ApplianceProfile(
            tenant_id=device.tenant_id,
            name=name,
            kw_signature=abs(spike.delta_kw),
            kw_tolerance=Decimal("0.15"),
            confirmed=True,
        )
        session.add(profile)

        spike.appliance_id = profile.id
        spike.status = "confirmed"

        await session.commit()
        logger.info(f"Appliance '{name}' saved for tenant {device.tenant_id}")


# ---------------------------------------------------------------------------
# Redis listener — runs in background thread alongside PTB event loop
# ---------------------------------------------------------------------------

async def redis_listener(app):
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(TELEGRAM_NOTIFY_CHANNEL)

    async for raw in pubsub.listen():
        if raw["type"] != "message":
            continue
        try:
            event = json.loads(raw["data"])
            if event.get("type") == "unknown_appliance":
                await handle_unknown_appliance(
                    app.bot, app.bot_data["engine"], event
                )
        except Exception as exc:
            logger.exception(f"Redis listener error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.bot_data["engine"] = engine

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("bill", cmd_bill))
    app.add_handler(CommandHandler("tips", cmd_tips))
    app.add_handler(CallbackQueryHandler(callback_appliance_name, pattern=r"^name:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def post_init(application):
        asyncio.ensure_future(redis_listener(application))

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
