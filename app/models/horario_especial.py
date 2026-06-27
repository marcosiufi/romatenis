from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HorarioEspecial(Base):
    __tablename__ = "horarios_especiais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    descricao: Mapped[str] = mapped_column(String(100), nullable=False)
    fechado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hora_abertura: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hora_fechamento: Mapped[int | None] = mapped_column(Integer, nullable=True)
