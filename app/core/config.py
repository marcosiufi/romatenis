from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://ranking:ranking@localhost:5432/ranking_tenis"
    SECRET_KEY: str = "dev-secret-key"
    ENVIRONMENT: str = "development"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ASAAS_API_KEY: str = ""
    ASAAS_BASE_URL: str = "https://sandbox.asaas.com/api/v3"
    ASAAS_WEBHOOK_TOKEN: str = ""  # token configurado no painel Asaas → Integrações → Webhooks

    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""

    # N8N — orquestrador de mensagens WhatsApp
    N8N_EVENTS_WEBHOOK_URL: str = ""   # URL do webhook N8N que recebe todos os eventos
    N8N_SECRET: str = ""               # Segredo compartilhado para N8N → backend


settings = Settings()
