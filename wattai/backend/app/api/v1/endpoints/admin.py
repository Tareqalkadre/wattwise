"""
Admin config endpoint.
Allows super-admins to get/set platform-wide config values:
  - premium_price_usd
  - spike_threshold_kw
  - free_tier_device_limit
  - etc.
Changes are written to DB and synced to Redis for instant pickup by workers.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import redis.asyncio as aioredis

from app.core.config import settings
from app.db.models import AdminConfig, User
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


class ConfigItem(BaseModel):
    key: str
    value: str
    description: str = ""


def require_superadmin(user: User = Depends(get_current_user)):
    if user.role != "superadmin":
        raise HTTPException(403, "Super-admin access required")
    return user


@router.get("/config")
async def list_config(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_superadmin),
):
    result = await session.execute(select(AdminConfig))
    items = result.scalars().all()
    return [{"key": i.key, "value": i.value, "description": i.description} for i in items]


@router.put("/config/{key}")
async def set_config(
    key: str,
    body: ConfigItem,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_superadmin),
):
    result = await session.execute(select(AdminConfig).where(AdminConfig.key == key))
    item = result.scalar_one_or_none()

    if item:
        item.value = body.value
        item.description = body.description or item.description
    else:
        item = AdminConfig(key=key, value=body.value, description=body.description)
        session.add(item)

    await session.commit()

    # Sync to Redis so workers pick it up immediately
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.set(f"cfg:{key}", body.value)
    await redis_client.aclose()

    return {"key": key, "value": body.value}


# Convenience: set subscription price
@router.put("/pricing/premium")
async def set_premium_price(
    price_usd: float,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_superadmin),
):
    """
    Update the monthly premium subscription price globally.
    Existing subscribers are grandfathered (Stripe handles proration).
    New subscribers get this price immediately.
    """
    result = await session.execute(
        select(AdminConfig).where(AdminConfig.key == "premium_price_usd")
    )
    item = result.scalar_one_or_none()
    if item:
        item.value = str(price_usd)
    else:
        item = AdminConfig(
            key="premium_price_usd",
            value=str(price_usd),
            description="Monthly premium subscription price in USD",
        )
        session.add(item)

    await session.commit()

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.set("cfg:premium_price_usd", str(price_usd))
    await redis_client.aclose()

    return {"message": f"Premium price updated to ${price_usd:.2f}/month"}
