import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


class TipoReserva(str, enum.Enum):
    RANKING = "ranking"
    LOCACAO_AVULSA = "locacao_avulsa"
    JOGO_AVULSO = "jogo_avulso"
    AULA = "aula"


class StatusReserva(str, enum.Enum):
    AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_hora_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_hora_fim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tipo: Mapped[TipoReserva] = mapped_column(pg_enum(TipoReserva), nullable=False)
    status: Mapped[StatusReserva] = mapped_column(
        pg_enum(StatusReserva), nullable=False, default=StatusReserva.CONFIRMADA
    )

    # Player do ranking responsável pela reserva (nullable para locações avulsas externas)
    jogador_responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    # Nome/telefone para locação avulsa de pessoa sem cadastro no ranking
    cliente_locacao_nome: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cliente_locacao_telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True, unique=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now(),
    )

    # Preenchido apenas para locação avulsa
    valor: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    jogador_responsavel: Mapped["Player | None"] = relationship(
        back_populates="bookings", foreign_keys=[jogador_responsavel_id]
    )
    match: Mapped["Match | None"] = relationship(back_populates="booking")
    payments: Mapped[list["Payment"]] = relationship(back_populates="booking")
