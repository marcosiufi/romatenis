from datetime import time

from sqlalchemy import Boolean, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SlotRanking(Base):
    __tablename__ = "slots_ranking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=segunda … 6=domingo
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fim: Mapped[time] = mapped_column(Time, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
