from datetime import datetime

from pydantic import BaseModel, Field

from app.models.subscription import FormaPagamento, PlanoAssinatura, StatusAssinatura


class SubscriptionCreate(BaseModel):
    player_id: int
    plano: PlanoAssinatura
    forma_pagamento: FormaPagamento
    valor_mensal: float = Field(gt=0, description="Valor mensal em R$")
    parcelas: int = Field(default=1, ge=1, le=12)


class SubscriptionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    player_id: int
    plano: PlanoAssinatura
    valor_mensal: float
    valor_total_ciclo: float
    forma_pagamento: FormaPagamento
    parcelas: int
    antecipacao_solicitada: bool
    status: StatusAssinatura
    data_inicio_ciclo: datetime
    data_expiracao: datetime
    gateway_subscription_id: str | None


class SubscriptionCreateOut(SubscriptionOut):
    """Retornado apenas na criação — inclui dados de pagamento Asaas."""

    payment_link: str | None = None
    pix_qrcode_base64: str | None = None
    pix_copia_e_cola: str | None = None
