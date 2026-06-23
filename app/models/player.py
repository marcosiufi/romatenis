import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


class NivelJogador(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    NAO_CLASSIFICADO = "nao_classificado"


class StatusJogador(str, enum.Enum):
    ATIVO = "ativo"
    INATIVO = "inativo"
    SUSPENSO = "suspenso"


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    telefone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    rating_atual: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    nivel: Mapped[NivelJogador] = mapped_column(
        pg_enum(NivelJogador), nullable=False, default=NivelJogador.NAO_CLASSIFICADO
    )
    partidas_computadas_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pontos_ranking_temporada_atual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    aceita_convites_sistema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Dados pessoais complementares
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True, unique=True)
    data_nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    apelido: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Endereço
    rua: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    pais: Mapped[str | None] = mapped_column(String(50), nullable=True, default="Brasil")
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)

    # Status de atividade (regras de expiração Fase 2)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=StatusJogador.ATIVO.value)
    data_inativacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ID do cliente no Asaas (preenchido na primeira cobrança)
    asaas_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    data_cadastro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="player")
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="jogador_responsavel", foreign_keys="Booking.jogador_responsavel_id"
    )
    participacoes: Mapped[list["MatchParticipant"]] = relationship(back_populates="player")
    whatsapp_logs: Mapped[list["WhatsAppMessageLog"]] = relationship(back_populates="player")
    convites: Mapped[list["MatchInvitationPlayer"]] = relationship(back_populates="player")
