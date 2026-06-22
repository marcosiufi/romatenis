import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.match import TipoPartida


class StatusConvite(str, enum.Enum):
    PENDENTE = "pendente"       # aguardando resposta do jogador
    CONFIRMADO = "confirmado"   # jogador aceitou
    RECUSADO = "recusado"       # jogador recusou
    EXPIRADO = "expirado"       # prazo de resposta esgotado
    CANCELADO = "cancelado"     # convite cancelado pelo sistema (ex: outro slot foi preenchido)


class StatusRodadaMatchmaking(str, enum.Enum):
    AGUARDANDO = "aguardando"         # convites enviados, aguardando confirmações
    CONFIRMADA = "confirmada"         # todos confirmaram → booking criado
    FALHOU = "falhou"                 # não foi possível fechar o jogo (recusas/expirações)


class MatchInvitation(Base):
    """
    Uma rodada de matchmaking para um slot específico.
    O sistema pode enviar múltiplas rodadas para o mesmo slot se jogadores recusarem.
    """
    __tablename__ = "match_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[TipoPartida] = mapped_column(Enum(TipoPartida), nullable=False)
    slot_data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[StatusRodadaMatchmaking] = mapped_column(
        Enum(StatusRodadaMatchmaking),
        nullable=False,
        default=StatusRodadaMatchmaking.AGUARDANDO,
    )

    # Prazo para todos responderem (ex: 2h antes do horário do jogo)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Preenchido quando todos confirmam e o booking é criado
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    jogadores: Mapped[list["MatchInvitationPlayer"]] = relationship(
        back_populates="invitation", cascade="all, delete-orphan"
    )
    booking: Mapped["Booking | None"] = relationship()


class MatchInvitationPlayer(Base):
    """Resposta individual de cada jogador convidado para uma rodada de matchmaking."""

    __tablename__ = "match_invitation_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invitation_id: Mapped[int] = mapped_column(
        ForeignKey("match_invitations.id"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    # Lado proposto (A ou B) — definido pelo algoritmo de matchmaking
    lado_proposto: Mapped[str] = mapped_column(String(1), nullable=False)  # "A" ou "B"

    status: Mapped[StatusConvite] = mapped_column(
        Enum(StatusConvite), nullable=False, default=StatusConvite.PENDENTE
    )
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # WAMID da mensagem WhatsApp enviada (para rastrear entrega e resposta)
    wamid_convite: Mapped[str | None] = mapped_column(String(255), nullable=True)

    invitation: Mapped["MatchInvitation"] = relationship(back_populates="jogadores")
    player: Mapped["Player"] = relationship(back_populates="convites")
