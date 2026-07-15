from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # MQTT
    MQTT_HOST: str = "mosquitto"
    MQTT_PORT: int = 8883
    MQTT_INTERNAL_USER: str
    MQTT_INTERNAL_PASSWORD: str
    MQTT_CA_PATH: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # Admin defaults
    DEFAULT_PREMIUM_PRICE_USD: float = 9.99

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]
    DOMAIN: str = "localhost"


settings = Settings()
