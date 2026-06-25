from datetime import date as date_type, datetime

from pydantic import BaseModel, Field

from app.models.subscription import FormaPagamento, PlanoAssinatura, StatusAssinatura


class SubscriptionCreate(BaseModel):
    player_id: int
    plano: PlanoAssinatura
    forma_pagamento: FormaPagamento
    valor_mensal: float = Field(gt=0, description="Valor mensal em R$")
    parcelas: int = Field(default=1, ge=1, le=12)


class SubscriptionRenovar(BaseModel):
    plano: PlanoAssinatura
    forma_pagamento: FormaPagamento = FormaPagamento.PIX_AVISTA


class SubscriptionAdminUpdate(BaseModel):
    status: StatusAssinatura
    data_pausa: datetime | None = None
    data_retorno_prevista: datetime | None = None
    notas: str | None = None


class PausaRequest(BaseModel):
    motivo: str
    data_inicio: date_type
    dias_pausa: int = Field(ge=1, le=15)


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
    data_pausa: datetime | None = None
    data_retorno_prevista: datetime | None = None
    gateway_subscription_id: str | None
    notas: str | None = None
    pausa_solicitada: bool = False
    pausa_motivo: str | None = None


class SubscriptionCreateOut(SubscriptionOut):
    """Retornado na criação e renovação — inclui dados de pagamento Asaas."""

    payment_link: str | None = None
    pix_qrcode_base64: str | None = None
    pix_copia_e_cola: str | None = None


class SubscriptionAdminOut(SubscriptionOut):
    """Retornado no admin — inclui dados do jogador."""

    player_nome: str | None = None
    player_email: str | None = None
