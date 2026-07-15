"""
Provisioning endpoint.
Called by the BLE provisioning web app after a meter is set up.
Registers the device and stores localization data for the tenant.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import Device, Tenant, TariffRule
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user
from app.db.models import User

router = APIRouter()


class LocalizationPayload(BaseModel):
    country: str
    city: str
    timezone: str
    currency: str
    tariff_type: str       # "flat" | "block" | "tou"
    flat_rate: float | None = None


class DeviceProvisionPayload(BaseModel):
    serial_number: str
    model: str             # SPM01 | SPM02
    location_label: str
    mqtt_topic_prefix: str
    localization: LocalizationPayload


@router.post("/complete")
async def complete_provisioning(
    body: DeviceProvisionPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # Update tenant localization
    tenant = await session.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    loc = body.localization
    tenant.country = loc.country
    tenant.city = loc.city
    tenant.timezone = loc.timezone
    tenant.currency = loc.currency

    # Register device
    result = await session.execute(
        select(Device).where(Device.serial_number == body.serial_number)
    )
    device = result.scalar_one_or_none()

    if device and device.tenant_id != user.tenant_id:
        raise HTTPException(409, "Device already registered to another tenant")

    if not device:
        device = Device(
            tenant_id=user.tenant_id,
            serial_number=body.serial_number,
            model=body.model,
            mqtt_topic_prefix=body.mqtt_topic_prefix,
            location_label=body.location_label,
            is_provisioned=True,
        )
        session.add(device)
    else:
        device.location_label = body.location_label
        device.mqtt_topic_prefix = body.mqtt_topic_prefix
        device.is_provisioned = True

    # Seed flat tariff rule if provided
    if loc.tariff_type == "flat" and loc.flat_rate:
        existing = await session.execute(
            select(TariffRule).where(TariffRule.tenant_id == user.tenant_id)
        )
        if not existing.scalars().first():
            rule = TariffRule(
                tenant_id=user.tenant_id,
                tier_name="Default",
                rate_per_kwh=loc.flat_rate,
            )
            session.add(rule)

    await session.commit()
    return {"message": "Device provisioned", "device_id": device.id}


@router.get("/tariff-presets/{country}/{city}")
async def get_tariff_presets(country: str, city: str):
    """
    Return known tariff presets for a country/city combination.
    In production: query your tariff database or a third-party API.
    """
    # Stub — replace with real data source
    presets = {
        ("Saudi Arabia", "Jeddah"): [
            {"tier": "Block 1", "from_kwh": 0, "to_kwh": 2000, "rate": 0.048},
            {"tier": "Block 2", "from_kwh": 2000, "to_kwh": 4000, "rate": 0.096},
            {"tier": "Block 3", "from_kwh": 4000, "to_kwh": None, "rate": 0.240},
        ],
        ("UAE", "Dubai"): [
            {"tier": "Slab 1", "from_kwh": 0, "to_kwh": 2000, "rate": 0.23},
            {"tier": "Slab 2", "from_kwh": 2000, "to_kwh": None, "rate": 0.38},
        ],
    }
    key = (country, city)
    return presets.get(key, [{"tier": "Flat", "from_kwh": 0, "to_kwh": None, "rate": 0.10}])
