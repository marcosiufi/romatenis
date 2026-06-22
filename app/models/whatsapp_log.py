import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


class TipoMensagem(str, enum.Enum):
    CONFIRMACAO_RESERVA = "confirmacao_reserva"
    LEMBRETE_PARTIDA = "lembrete_partida"
    SOLICITACAO_PLACAR = "solicitacao_placar"
    RESULTADO_RATING = "resultado_rating"
    COBRANCA = "cobranca"
    AVISO_EXPIRACAO = "aviso_expiracao"
    CONVITE_MATCHMAKING = "convite_matchmaking"


class StatusEnvio(str, enum.Enum):
    ENVIADO = "enviado"
    FALHOU = "falhou"
    PENDENTE = "pendente"


class WhatsAppMessageLog(Base):
    __tablename__ = "whatsapp_message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    tipo: Mapped[TipoMensagem] = mapped_column(pg_enum(TipoMensagem), nullable=False)
    status_envio: Mapped[StatusEnvio] = mapped_column(
        pg_enum(StatusEnvio), nullable=False, default=StatusEnvio.PENDENTE
    )
    # ID retornado pela Meta Cloud API
    wamid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    player: Mapped["Player"] = relationship(back_populates="whatsapp_logs")
