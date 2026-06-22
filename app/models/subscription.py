import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PlanoAssinatura(str, enum.Enum):
    MENSAL = "mensal"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class FormaPagamento(str, enum.Enum):
    PIX_AVISTA = "pix_avista"
    BOLETO_AVISTA = "boleto_avista"
    CARTAO_PARCELADO = "cartao_parcelado"


class StatusAssinatura(str, enum.Enum):
    ATIVA = "ativa"
    EXPIRADA = "expirada"
    INADIMPLENTE = "inadimplente"
    CANCELADA = "cancelada"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    plano: Mapped[PlanoAssinatura] = mapped_column(Enum(PlanoAssinatura), nullable=False)
    valor_mensal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    valor_total_ciclo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    forma_pagamento: Mapped[FormaPagamento] = mapped_column(Enum(FormaPagamento), nullable=False)
    parcelas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    antecipacao_solicitada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[StatusAssinatura] = mapped_column(
        Enum(StatusAssinatura), nullable=False, default=StatusAssinatura.ATIVA
    )
    data_inicio_ciclo: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_expiracao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    gateway_subscription_id: Mapped[str | None] = mapped_column(nullable=True)

    player: Mapped["Player"] = relationship(back_populates="subscriptions")
    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription")
