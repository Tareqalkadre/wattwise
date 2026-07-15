"""
MQTT Ingestion Worker
Subscribes to SPM01/#, SPM02/#, SDM01/#
Parses readings → writes to TimescaleDB → publishes spike events to Redis.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import aiomqtt
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.db.models import Device, Reading

logger = logging.getLogger(__name__)

TOPIC_PATTERNS = ["SPM01/#", "SPM02/#", "SDM01/#"]
SPIKE_CHANNEL = "spike_events"


async def get_device_by_topic(session: AsyncSession, serial: str) -> Device | None:
    result = await session.execute(
        select(Device).where(Device.serial_number == serial)
    )
    return result.scalar_one_or_none()


def parse_reading(payload: dict, device_id: str) -> Reading:
    return Reading(
        device_id=device_id,
        time=datetime.now(timezone.utc),
        voltage=payload.get("Voltage") or payload.get("voltageC"),
        current_a=payload.get("Current") or payload.get("currentC"),
        active_power=payload.get("ActivePower") or payload.get("TotalActivePower"),
        power_factor=payload.get("PowerFactor") or payload.get("TotalPowerFactor"),
        frequency=payload.get("Frequency") or payload.get("frequency"),
        forward_energy=payload.get("ForwardEnergy") or payload.get("forwardenergy"),
        reverse_energy=payload.get("ReverseEnergy") or payload.get("reverseenergy"),
    )


async def detect_spike(redis_client, device_id: str, current_kw: float):
    """
    Compare current active power to last known value.
    Publish to Redis pub/sub if delta exceeds threshold.
    Threshold is read from admin_config via Redis cache.
    """
    key = f"last_kw:{device_id}"
    last_raw = await redis_client.get(key)
    await redis_client.setex(key, 300, str(current_kw))  # 5-min TTL

    if last_raw is None:
        return

    last_kw = float(last_raw)
    delta = current_kw - last_kw

    threshold_raw = await redis_client.get("cfg:spike_threshold_kw")
    threshold = float(threshold_raw) if threshold_raw else 0.5  # default 0.5 kW

    if abs(delta) >= threshold:
        event = {
            "device_id": device_id,
            "delta_kw": round(delta, 3),
            "current_kw": round(current_kw, 3),
            "direction": "up" if delta > 0 else "down",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        await redis_client.publish(SPIKE_CHANNEL, json.dumps(event))
        logger.info(f"Spike detected: {event}")


async def main():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    tls_context = None
    if settings.MQTT_CA_PATH:
        import ssl
        tls_context = ssl.create_default_context(cafile=settings.MQTT_CA_PATH)

    logger.info("Ingestion worker starting…")

    async with aiomqtt.Client(
        hostname=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        username=settings.MQTT_INTERNAL_USER,
        password=settings.MQTT_INTERNAL_PASSWORD,
        tls_context=tls_context,
    ) as client:
        for pattern in TOPIC_PATTERNS:
            await client.subscribe(pattern)
        logger.info(f"Subscribed to {TOPIC_PATTERNS}")

        async for message in client.messages:
            topic = str(message.topic)
            if not topic.endswith("/data"):
                continue

            try:
                payload = json.loads(message.payload)
                # Topic format: SPM01/{serial}/data
                parts = topic.split("/")
                serial = parts[1] if len(parts) >= 3 else None
                if not serial:
                    continue

                async with AsyncSession(engine) as session:
                    device = await get_device_by_topic(session, serial)
                    if not device:
                        logger.warning(f"Unknown serial {serial} — skipping")
                        continue

                    reading = parse_reading(payload, device.id)
                    session.add(reading)

                    # Update device last_seen
                    device.last_seen_at = datetime.now(timezone.utc)
                    if payload.get("FWVersion"):
                        device.firmware_version = payload["FWVersion"]

                    await session.commit()

                # Spike detection (non-blocking, fires into Redis pub/sub)
                kw_raw = payload.get("ActivePower") or payload.get("TotalActivePower") or 0
                if kw_raw:
                    await detect_spike(redis_client, device.id, float(kw_raw))

            except Exception as exc:
                logger.exception(f"Error processing {topic}: {exc}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
