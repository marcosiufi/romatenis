from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # encoding explícito: SMTP_FROM_NAME tem acento e um .env salvo noutra
    # codificação quebraria a leitura de forma difícil de diagnosticar
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATABASE_URL: str = "postgresql+asyncpg://ranking:ranking@localhost:5432/ranking_tenis"
    SECRET_KEY: str = "dev-secret-key"
    ENVIRONMENT: str = "development"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DOMAIN: str = "https://romatenis.com.br"

    ASAAS_API_KEY: str = ""       # armazenado em base64 no .env para evitar interpolação do $
    ASAAS_BASE_URL: str = "https://api.asaas.com/v3"

    @property
    def asaas_api_key(self) -> str:
        """Decodifica a chave Asaas de base64 (necessário pois a chave contém $ que o Docker Compose interpola)."""
        if not self.ASAAS_API_KEY:
            return ""
        import base64
        try:
            return base64.b64decode(self.ASAAS_API_KEY).decode()
        except Exception:
            return self.ASAAS_API_KEY  # fallback: valor literal
    ASAAS_WEBHOOK_TOKEN: str = ""

    # Preços padrão por plano (R$) — sobrescrevíveis pelo admin na criação
    PRECO_MENSAL: float = 89.90
    PRECO_TRIMESTRAL: float = 239.90
    PRECO_SEMESTRAL: float = 449.90
    PRECO_ANUAL: float = 839.90

    # SMTP para notificações por e-mail
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""      # conta usada para autenticar
    SMTP_PASS: str = ""
    # Remetente exibido. Deixe vazio para usar o SMTP_USER. Só preencha com um
    # endereço diferente se o servidor autorizar enviar em nome dele (alias
    # verificado no Gmail ou caixa do próprio domínio) — caso contrário o
    # provedor rejeita ou a mensagem cai em spam.
    SMTP_FROM: str = ""
    SMTP_FROM_NAME: str = "Roma Tênis"

    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""

    N8N_EVENTS_WEBHOOK_URL: str = ""
    N8N_SECRET: str = ""

    # Autentique (contratos digitais)
    AUTENTIQUE_API_KEY: str = ""
    AUTENTIQUE_WEBHOOK_SECRET: str = ""


settings = Settings()
