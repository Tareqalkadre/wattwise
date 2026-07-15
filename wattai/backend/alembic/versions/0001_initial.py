"""Initial schema with TimescaleDB hypertable

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create all tables via SQLAlchemy metadata
    # (In practice, import Base.metadata.create_all or use --autogenerate)

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64)),
        sa.Column("city", sa.String(64)),
        sa.Column("timezone", sa.String(64)),
        sa.Column("currency", sa.String(8)),
        sa.Column("tariff_config", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("monthly_fee", sa.Numeric(8, 2)),
        sa.Column("stripe_customer_id", sa.String(64)),
        sa.Column("stripe_subscription_id", sa.String(64)),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("current_period_end", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("telegram_chat_id", sa.String(32)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_telegram", "users", ["telegram_chat_id"])

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial_number", sa.String(32), unique=True, nullable=False),
        sa.Column("model", sa.String(32)),
        sa.Column("mqtt_topic_prefix", sa.String(64)),
        sa.Column("ble_password_hash", sa.String(128)),
        sa.Column("location_label", sa.String(64)),
        sa.Column("firmware_version", sa.String(16)),
        sa.Column("is_provisioned", sa.Boolean, server_default="false"),
        sa.Column("last_seen_at", sa.DateTime),
        sa.Column("provisioned_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_devices_serial", "devices", ["serial_number"])

    op.create_table(
        "readings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("time", sa.DateTime, nullable=False),
        sa.Column("voltage", sa.Numeric(7, 2)),
        sa.Column("current_a", sa.Numeric(8, 3)),
        sa.Column("active_power", sa.Numeric(8, 3)),
        sa.Column("power_factor", sa.Numeric(5, 3)),
        sa.Column("frequency", sa.Numeric(5, 2)),
        sa.Column("forward_energy", sa.Numeric(12, 4)),
        sa.Column("reverse_energy", sa.Numeric(12, 4)),
    )
    op.create_index("ix_readings_device_time", "readings", ["device_id", "time"])

    # ---- Convert readings to TimescaleDB hypertable ----
    op.execute("SELECT create_hypertable('readings', 'time', if_not_exists => TRUE);")
    # Optional: auto-compress chunks older than 7 days
    op.execute("""
        SELECT add_compression_policy('readings', INTERVAL '7 days')
        ON CONFLICT DO NOTHING;
    """)

    op.create_table(
        "appliance_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("kw_signature", sa.Numeric(7, 3), nullable=False),
        sa.Column("kw_tolerance", sa.Numeric(6, 3), server_default="0.15"),
        sa.Column("category", sa.String(32)),
        sa.Column("confirmed", sa.Boolean, server_default="false"),
        sa.Column("detection_count", sa.Numeric, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "spike_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appliance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("appliance_profiles.id"), nullable=True),
        sa.Column("delta_kw", sa.Numeric(7, 3), nullable=False),
        sa.Column("direction", sa.String(4), server_default="up"),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("detected_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime),
    )

    op.create_table(
        "tariff_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier_name", sa.String(32)),
        sa.Column("rate_per_kwh", sa.Numeric(8, 4), nullable=False),
        sa.Column("from_kwh", sa.Numeric(10, 2), server_default="0"),
        sa.Column("to_kwh", sa.Numeric(10, 2)),
        sa.Column("time_of_use_start", sa.String(5)),
        sa.Column("time_of_use_end", sa.String(5)),
        sa.Column("day_types", sa.String(16), server_default="all"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "admin_config",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Seed default admin config
    op.execute("""
        INSERT INTO admin_config (id, key, value, description) VALUES
        (gen_random_uuid(), 'premium_price_usd', '9.99', 'Monthly premium subscription price'),
        (gen_random_uuid(), 'spike_threshold_kw', '0.5', 'Minimum kW delta to trigger spike detection'),
        (gen_random_uuid(), 'free_tier_device_limit', '2', 'Max devices on free plan');
    """)


def downgrade():
    for table in ["admin_config", "tariff_rules", "spike_events", "appliance_profiles",
                  "readings", "devices", "users", "subscriptions", "tenants"]:
        op.drop_table(table)
