import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


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
    tipo: Mapped[TipoPartida] = mapped_column(pg_enum(TipoPartida), nullable=False)
    status: Mapped[StatusPartida] = mapped_column(
        pg_enum(StatusPartida), nullable=False, default=StatusPartida.AGENDADO
    )
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duracao_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Placar como JSON: {"lado_A": [6, 4], "lado_B": [4, 6, 7]} (games por set)
    placar: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lado_vencedor: Mapped[str | None] = mapped_column(String(1), nullable=True)  # "A" ou "B"

    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)

    # Jogo avulso: membro joga com convidado(s) de fora. Ocupa a cota semanal,
    # mas não gera pontos nem Elo para ninguém — por isso não aceita placar.
    avulso: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Evita reenviar o lembrete a cada ciclo do scheduler
    lembrete_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Cancelamento tardio: marca quem cancelou fora do prazo. O jogo vira WO
    # (sem pontuar) e só conta no saldo semanal desse jogador — os demais
    # participantes recuperam a vaga.
    cancelado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )

    season: Mapped["Season | None"] = relationship(back_populates="matches")
    participantes: Mapped[list["MatchParticipant"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    booking: Mapped["Booking | None"] = relationship(back_populates="match")


class MatchParticipant(Base):
    """
    Associação entre Match e um jogador, com snapshot de rating e pontos atribuídos.

    Exatamente um entre player_id (membro do ranking) e convidado_id (jogador de
    fora, apenas em jogos avulsos) é preenchido.
    """

    __tablename__ = "match_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    convidado_id: Mapped[int | None] = mapped_column(ForeignKey("convidados.id"), nullable=True)
    lado: Mapped[LadoPartida] = mapped_column(pg_enum(LadoPartida), nullable=False)

    rating_antes: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_depois: Mapped[float | None] = mapped_column(Float, nullable=True)
    pontos_atribuidos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="participantes")
    player: Mapped["Player | None"] = relationship(back_populates="participacoes")
    convidado: Mapped["Convidado | None"] = relationship(back_populates="participacoes")
