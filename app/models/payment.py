import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


class MetodoPagamento(str, enum.Enum):
    PIX = "pix"
    CARTAO = "cartao"
    BOLETO = "boleto"


class StatusPagamento(str, enum.Enum):
    PENDENTE = "pendente"
    PAGO = "pago"
    FALHOU = "falhou"
    ESTORNADO = "estornado"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Uma cobrança pertence a uma reserva OU a uma assinatura, não ambas
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )

    valor: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    metodo: Mapped[MetodoPagamento] = mapped_column(pg_enum(MetodoPagamento), nullable=False)
    status: Mapped[StatusPagamento] = mapped_column(
        pg_enum(StatusPagamento), nullable=False, default=StatusPagamento.PENDENTE
    )

    gateway_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    booking: Mapped["Booking | None"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="payments")
