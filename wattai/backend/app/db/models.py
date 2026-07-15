"""
SQLAlchemy ORM models. TimescaleDB hypertable for `readings` is created
via Alembic migration (see alembic/versions/).
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Numeric, DateTime, ForeignKey,
    Text, JSON, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tenant (organisation / household / building)
# ---------------------------------------------------------------------------
class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)
    country = Column(String(64))          # e.g. "Saudi Arabia"
    city = Column(String(64))             # e.g. "Jeddah"
    timezone = Column(String(64))         # e.g. "Asia/Riyadh"
    currency = Column(String(8))          # e.g. "SAR"
    tariff_config = Column(JSON)          # cached tariff snapshot
    created_at = Column(DateTime, server_default=func.now())

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    appliance_profiles = relationship("ApplianceProfile", back_populates="tenant", cascade="all, delete-orphan")
    tariff_rules = relationship("TariffRule", back_populates="tenant", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default="member")  # owner | admin | member
    telegram_chat_id = Column(String(32), unique=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    tenant = relationship("Tenant", back_populates="users")


# ---------------------------------------------------------------------------
# Subscription (per tenant, managed via Stripe)
# ---------------------------------------------------------------------------
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    plan = Column(String(16), nullable=False, default="free")  # free | premium
    monthly_fee = Column(Numeric(8, 2))
    stripe_customer_id = Column(String(64))
    stripe_subscription_id = Column(String(64))
    status = Column(String(16), default="active")  # active | past_due | canceled
    current_period_end = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="subscriptions")


# ---------------------------------------------------------------------------
# Device (meter)
# ---------------------------------------------------------------------------
class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    serial_number = Column(String(32), unique=True, nullable=False, index=True)
    model = Column(String(32))           # SPM01 | SPM02
    mqtt_topic_prefix = Column(String(64))  # e.g. "SPM01/18132672040792"
    ble_password_hash = Column(String(128)) # bcrypt of last known BLE password
    location_label = Column(String(64))    # "Main panel", "Garage", etc.
    firmware_version = Column(String(16))
    is_provisioned = Column(Boolean, default=False)
    last_seen_at = Column(DateTime)
    provisioned_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    tenant = relationship("Tenant", back_populates="devices")
    readings = relationship("Reading", back_populates="device", cascade="all, delete-orphan")
    spike_events = relationship("SpikeEvent", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "serial_number", name="uq_tenant_serial"),
    )


# ---------------------------------------------------------------------------
# Reading — TimescaleDB hypertable on `time`
# ---------------------------------------------------------------------------
class Reading(Base):
    __tablename__ = "readings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    device_id = Column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    time = Column(DateTime, nullable=False, index=True)  # hypertable partition key
    voltage = Column(Numeric(7, 2))
    current_a = Column(Numeric(8, 3))
    active_power = Column(Numeric(8, 3))    # kW
    power_factor = Column(Numeric(5, 3))
    frequency = Column(Numeric(5, 2))
    forward_energy = Column(Numeric(12, 4)) # kWh
    reverse_energy = Column(Numeric(12, 4)) # kWh

    device = relationship("Device", back_populates="readings")

    __table_args__ = (
        Index("ix_readings_device_time", "device_id", "time"),
    )


# ---------------------------------------------------------------------------
# Appliance profile — learned via MQTT spike + Telegram confirmation
# ---------------------------------------------------------------------------
class ApplianceProfile(Base):
    __tablename__ = "appliance_profiles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(64), nullable=False)  # "Air conditioner", "Washing machine"
    kw_signature = Column(Numeric(7, 3), nullable=False)  # median delta kW
    kw_tolerance = Column(Numeric(6, 3), default=0.15)    # ±kW window for matching
    category = Column(String(32))              # HVAC | kitchen | laundry | lighting
    confirmed = Column(Boolean, default=False) # True after user confirms in Telegram
    detection_count = Column(Numeric, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="appliance_profiles")
    spike_events = relationship("SpikeEvent", back_populates="appliance")


# ---------------------------------------------------------------------------
# Spike event — every detected kW jump
# ---------------------------------------------------------------------------
class SpikeEvent(Base):
    __tablename__ = "spike_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    device_id = Column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    appliance_id = Column(UUID(as_uuid=False), ForeignKey("appliance_profiles.id"), nullable=True)
    delta_kw = Column(Numeric(7, 3), nullable=False)
    direction = Column(String(4), default="up")  # up | down
    status = Column(String(16), default="pending")  # pending | matched | confirmed | ignored
    detected_at = Column(DateTime, server_default=func.now())
    confirmed_at = Column(DateTime)

    device = relationship("Device", back_populates="spike_events")
    appliance = relationship("ApplianceProfile", back_populates="spike_events")


# ---------------------------------------------------------------------------
# Tariff rules — per tenant, supports tiered + TOU pricing
# ---------------------------------------------------------------------------
class TariffRule(Base):
    __tablename__ = "tariff_rules"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    tier_name = Column(String(32))             # "Block 1", "Peak", "Off-peak"
    rate_per_kwh = Column(Numeric(8, 4), nullable=False)
    from_kwh = Column(Numeric(10, 2), default=0)      # block tariff lower bound
    to_kwh = Column(Numeric(10, 2))                   # NULL = unlimited
    time_of_use_start = Column(String(5))              # "08:00" — optional TOU
    time_of_use_end = Column(String(5))                # "22:00"
    day_types = Column(String(16), default="all")      # all | weekday | weekend
    created_at = Column(DateTime, server_default=func.now())

    tenant = relationship("Tenant", back_populates="tariff_rules")


# ---------------------------------------------------------------------------
# Admin config — key/value store for platform-wide settings
# (e.g. premium_price_usd, spike_threshold_kw, free_tier_device_limit)
# ---------------------------------------------------------------------------
class AdminConfig(Base):
    __tablename__ = "admin_config"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
