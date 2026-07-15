from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import Subscription, User
from app.db.session import get_session
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/status")
async def subscription_status(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Subscription).where(Subscription.tenant_id == user.tenant_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"plan": "free", "status": "active"}
    return {
        "plan": sub.plan,
        "status": sub.status,
        "monthly_fee": float(sub.monthly_fee or 0),
        "current_period_end": sub.current_period_end,
    }


@router.post("/upgrade")
async def upgrade_to_premium(user: User = Depends(get_current_user)):
    """
    Returns a Stripe Checkout URL.
    Full Stripe integration: create customer → create checkout session → webhook confirms.
    """
    return {
        "checkout_url": "https://checkout.stripe.com/pay/...",
        "message": "Redirect user to checkout_url to complete upgrade",
    }
