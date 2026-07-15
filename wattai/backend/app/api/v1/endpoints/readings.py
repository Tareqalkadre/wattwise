from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone, timedelta

from app.db.models import Reading, Device, User
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/live")
async def live_readings(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Latest reading per device for the tenant."""
    result = await session.execute(
        select(Reading)
        .join(Device, Device.id == Reading.device_id)
        .where(Device.tenant_id == user.tenant_id)
        .order_by(Reading.time.desc())
        .limit(10)
    )
    readings = result.scalars().all()
    return [
        {
            "device_id": r.device_id,
            "time": r.time,
            "active_power": float(r.active_power or 0),
            "voltage": float(r.voltage or 0),
            "current_a": float(r.current_a or 0),
            "power_factor": float(r.power_factor or 0),
            "frequency": float(r.frequency or 0),
            "forward_energy": float(r.forward_energy or 0),
        }
        for r in readings
    ]


@router.get("/history")
async def reading_history(
    device_id: str,
    hours: int = Query(24, ge=1, le=720),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Time-series readings for the dashboard charts."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        select(Reading)
        .join(Device, Device.id == Reading.device_id)
        .where(
            Device.tenant_id == user.tenant_id,
            Reading.device_id == device_id,
            Reading.time >= since,
        )
        .order_by(Reading.time.asc())
    )
    readings = result.scalars().all()
    return [
        {"time": r.time.isoformat(), "kw": float(r.active_power or 0)}
        for r in readings
    ]
