import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StatusTemporada(str, enum.Enum):
    ATIVA = "ativa"
    ENCERRADA = "encerrada"


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_fim: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[StatusTemporada] = mapped_column(
        Enum(StatusTemporada), nullable=False, default=StatusTemporada.ATIVA
    )
    # Snapshot do ranking no momento do encerramento: [{player_id, nome, pontos, posicao}]
    ranking_final: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    matches: Mapped[list["Match"]] = relationship(back_populates="season")
