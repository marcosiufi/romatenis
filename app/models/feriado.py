from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Feriado(Base):
    __tablename__ = "feriados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String(100), nullable=False)
    # Se True, apenas mês+dia são usados — repete todo ano
    recorrente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
