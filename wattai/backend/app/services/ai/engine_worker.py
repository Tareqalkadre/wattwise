"""
AI Engine Worker
Subscribes to Redis spike_events channel.
For Premium tenants:
  1. Tries to match spike to known appliance profiles.
  2. If unmatched → asks user via Telegram bot.
  3. Persists new profiles after confirmation.
  4. Publishes load-pacing and bill-optimization advice.
"""
import asyncio
import json
import logging
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.db.models import (
    ApplianceProfile, Device, SpikeEvent, Subscription, Tenant,
)

logger = logging.getLogger(__name__)
SPIKE_CHANNEL = "spike_events"
TELEGRAM_NOTIFY_CHANNEL = "telegram_notify"


async def get_premium_tenant(session: AsyncSession, device_id: str) -> Tenant | None:
    """Return tenant only if subscription is premium+active."""
    result = await session.execute(
        select(Tenant)
        .join(Device, Device.tenant_id == Tenant.id)
        .join(Subscription, Subscription.tenant_id == Tenant.id)
        .where(
            Device.id == device_id,
            Subscription.plan == "premium",
            Subscription.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def match_appliance(
    session: AsyncSession, tenant_id: str, delta_kw: float
) -> ApplianceProfile | None:
    """Find confirmed appliance whose signature ± tolerance covers delta_kw."""
    result = await session.execute(
        select(ApplianceProfile).where(
            ApplianceProfile.tenant_id == tenant_id,
            ApplianceProfile.confirmed == True,
        )
    )
    profiles = result.scalars().all()
    for p in profiles:
        sig = float(p.kw_signature)
        tol = float(p.kw_tolerance)
        if abs(abs(delta_kw) - sig) <= tol:
            return p
    return None


async def create_unconfirmed_spike(
    session: AsyncSession, device_id: str, delta_kw: float
) -> SpikeEvent:
    spike = SpikeEvent(
        device_id=device_id,
        delta_kw=Decimal(str(round(delta_kw, 3))),
        direction="up" if delta_kw > 0 else "down",
        status="pending",
    )
    session.add(spike)
    await session.flush()
    return spike


async def notify_telegram(redis_client, tenant_id: str, spike_id: str, delta_kw: float):
    """Push a message to the Telegram bot via Redis pub/sub."""
    msg = {
        "type": "unknown_appliance",
        "tenant_id": tenant_id,
        "spike_id": spike_id,
        "delta_kw": round(abs(delta_kw), 2),
    }
    await redis_client.publish(TELEGRAM_NOTIFY_CHANNEL, json.dumps(msg))


async def process_spike(session: AsyncSession, redis_client, event: dict):
    device_id = event["device_id"]
    delta_kw = event["delta_kw"]

    # Only run AI features for premium tenants
    tenant = await get_premium_tenant(session, device_id)
    if not tenant:
        return

    # Try to match existing profile
    appliance = await match_appliance(session, tenant.id, delta_kw)

    if appliance:
        # Known appliance — log matched event
        spike = SpikeEvent(
            device_id=device_id,
            appliance_id=appliance.id,
            delta_kw=Decimal(str(round(delta_kw, 3))),
            direction="up" if delta_kw > 0 else "down",
            status="matched",
        )
        session.add(spike)
        # Increment detection count
        appliance.detection_count = (appliance.detection_count or 0) + 1
        await session.commit()
        logger.info(f"Spike matched: {appliance.name} ({delta_kw} kW)")

    else:
        # Unknown — create pending spike and ask user via Telegram
        spike = await create_unconfirmed_spike(session, device_id, delta_kw)
        await session.commit()
        await notify_telegram(redis_client, tenant.id, spike.id, delta_kw)
        logger.info(f"Unknown spike {delta_kw} kW — Telegram query sent")


async def main():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(SPIKE_CHANNEL)

    logger.info("AI engine worker listening for spikes…")

    async for raw in pubsub.listen():
        if raw["type"] != "message":
            continue
        try:
            event = json.loads(raw["data"])
            async with AsyncSession(engine) as session:
                await process_spike(session, redis_client, event)
        except Exception as exc:
            logger.exception(f"AI engine error: {exc}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
