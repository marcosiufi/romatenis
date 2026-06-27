import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, pg_enum


class StatusListaEspera(str, enum.Enum):
    AGUARDANDO = "aguardando"
    CONVOCADO  = "convocado"   # notificado, tem 48h para confirmar
    EXPIRADO   = "expirado"    # não confirmou em 48h
    ATIVADO    = "ativado"     # tornou-se assinante
    REMOVIDO   = "removido"    # removido pela administração ou pelo próprio


class ListaEspera(Base):
    __tablename__ = "lista_espera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)

    status: Mapped[StatusListaEspera] = mapped_column(
        pg_enum(StatusListaEspera), nullable=False, default=StatusListaEspera.AGUARDANDO
    )
    data_inscricao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_convocacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_expiracao_convocacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notas: Mapped[str | None] = mapped_column(String, nullable=True)

    player: Mapped["Player"] = relationship("Player")
