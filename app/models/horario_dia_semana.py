from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

DIAS_NOMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


class HorarioDiaSemana(Base):
    __tablename__ = "horarios_dia_semana"

    dia_semana: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0=seg ... 6=dom
    aberto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hora_abertura: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    hora_fechamento: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
