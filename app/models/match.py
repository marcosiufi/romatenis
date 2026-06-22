import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TipoPartida(str, enum.Enum):
    SIMPLES = "simples"
    DUPLAS = "duplas"


class StatusPartida(str, enum.Enum):
    AGENDADO = "agendado"
    REALIZADO = "realizado"
    CANCELADO_SEM_PLACAR = "cancelado_sem_placar"
    WO = "wo"


class LadoPartida(str, enum.Enum):
    A = "A"
    B = "B"


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[TipoPartida] = mapped_column(Enum(TipoPartida), nullable=False)
    status: Mapped[StatusPartida] = mapped_column(
        Enum(StatusPartida), nullable=False, default=StatusPartida.AGENDADO
    )
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duracao_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Placar como JSON: {"lado_A": [6, 4], "lado_B": [4, 6, 7]} (games por set)
    placar: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lado_vencedor: Mapped[str | None] = mapped_column(String(1), nullable=True)  # "A" ou "B"

    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)

    season: Mapped["Season | None"] = relationship(back_populates="matches")
    participantes: Mapped[list["MatchParticipant"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    booking: Mapped["Booking | None"] = relationship(back_populates="match")


class MatchParticipant(Base):
    """Associação entre Match e Player, com snapshot de rating e pontos atribuídos."""

    __tablename__ = "match_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    lado: Mapped[LadoPartida] = mapped_column(Enum(LadoPartida), nullable=False)

    rating_antes: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_depois: Mapped[float | None] = mapped_column(Float, nullable=True)
    pontos_atribuidos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="participantes")
    player: Mapped["Player"] = relationship(back_populates="participacoes")
