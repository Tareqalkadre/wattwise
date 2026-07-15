from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import Device, User
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/")
async def list_devices(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Device).where(Device.tenant_id == user.tenant_id)
    )
    devices = result.scalars().all()
    return [
        {
            "id": d.id,
            "serial_number": d.serial_number,
            "model": d.model,
            "location_label": d.location_label,
            "is_provisioned": d.is_provisioned,
            "last_seen_at": d.last_seen_at,
            "firmware_version": d.firmware_version,
        }
        for d in devices
    ]
