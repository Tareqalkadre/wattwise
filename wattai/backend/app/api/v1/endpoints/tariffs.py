from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import TariffRule, User
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


class TariffRuleIn(BaseModel):
    tier_name: str
    rate_per_kwh: float
    from_kwh: float = 0
    to_kwh: float | None = None
    time_of_use_start: str | None = None
    time_of_use_end: str | None = None
    day_types: str = "all"


@router.get("/")
async def list_tariffs(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(TariffRule).where(TariffRule.tenant_id == user.tenant_id)
    )
    rules = result.scalars().all()
    return [
        {
            "id": r.id,
            "tier_name": r.tier_name,
            "rate_per_kwh": float(r.rate_per_kwh),
            "from_kwh": float(r.from_kwh),
            "to_kwh": float(r.to_kwh) if r.to_kwh else None,
            "time_of_use_start": r.time_of_use_start,
            "time_of_use_end": r.time_of_use_end,
        }
        for r in rules
    ]


@router.post("/")
async def create_tariff(
    body: TariffRuleIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rule = TariffRule(tenant_id=user.tenant_id, **body.model_dump())
    session.add(rule)
    await session.commit()
    return {"id": rule.id, "message": "Tariff rule created"}
