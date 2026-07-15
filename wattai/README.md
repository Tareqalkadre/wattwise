# WattAI — SaaS Energy Monitoring Platform

Multi-tenant energy monitoring SaaS built on SPM01/SPM02 smart meters.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python 3.12) |
| Time-series DB | TimescaleDB (PostgreSQL 16) |
| Relational DB | PostgreSQL (same instance) |
| Message broker | Mosquitto 2 (MQTT over TLS) |
| Cache / pub-sub | Redis 7 |
| AI workers | Python asyncio services |
| Telegram bot | python-telegram-bot 21 |
| Frontend | React 18 + Vite + Recharts |
| Reverse proxy | Nginx |
| Billing | Stripe |
| Containers | Docker Compose |

## Quick start (local dev)

```bash
cp .env.example .env          # fill in your values
docker compose up -d postgres redis mosquitto
docker compose run --rm backend alembic upgrade head
docker compose up
```

Dashboard: http://localhost → nginx → React SPA
API docs:   http://localhost/api/docs

## Directory structure

```
wattai/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # FastAPI routers
│   │   ├── core/               # Config, security
│   │   ├── db/                 # Models, session
│   │   └── services/
│   │       ├── ai/             # AI engine worker
│   │       ├── mqtt/           # Ingestion worker
│   │       └── telegram/       # Telegram bot
│   ├── alembic/                # DB migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/              # Dashboard, Provision, Login, Upgrade
│   │   ├── components/         # Charts, cards, nav
│   │   ├── hooks/              # useAuth, useReadings
│   │   └── lib/                # api.ts (axios), queryClient
│   └── Dockerfile
├── infra/
│   ├── mosquitto/              # mosquitto.conf, passwd, acl
│   └── nginx/                  # nginx.conf
├── docker-compose.yml
└── .env.example
```

## Subscription tiers

| Feature | Free | Premium |
|---------|------|---------|
| Devices | 2 | Unlimited |
| Live readings | Yes | Yes |
| 24-h history | Yes | Yes |
| Appliance detection | No | Yes |
| Unknown load alerts | No | Yes (Telegram) |
| Bill optimisation | No | Yes |
| Load-pacing tips | No | Yes |
| Tariff tiers (block/TOU) | No | Yes |
| Telegram bot | Basic | Full AI |

## Changing subscription price

Via admin API (requires superadmin token):
```bash
curl -X PUT https://app.yourdomain.com/api/v1/admin/pricing/premium \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "price_usd=12.99"
```

Or via the admin_config table directly:
```sql
UPDATE admin_config SET value = '12.99' WHERE key = 'premium_price_usd';
```
Workers pick up the change from Redis within seconds.

## Production deployment

1. Point DNS: `app.yourdomain.com` → VPS IP, `mqtt.yourdomain.com` → VPS IP
2. `certbot certonly --standalone -d app.yourdomain.com -d mqtt.yourdomain.com`
3. Edit `infra/nginx/nginx.conf` and `infra/mosquitto/mosquitto.conf` with your domain
4. Set all `.env` values
5. `docker compose up -d`
6. `docker compose exec backend alembic upgrade head`
7. Create MQTT users: `docker compose exec mosquitto mosquitto_passwd /mosquitto/config/passwd meter_spm01`

## AI spike detection tuning

Edit `admin_config` via API:
- `spike_threshold_kw` — minimum delta to trigger (default 0.5 kW)
- `free_tier_device_limit` — max devices on free plan (default 2)
- `premium_price_usd` — monthly charge (default 9.99)
