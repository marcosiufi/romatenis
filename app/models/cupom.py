from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Cupom(Base):
    """Cupom de desconto percentual, com prazo e limite de usos opcionais."""

    __tablename__ = "cupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    codigo: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    percentual: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..100
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Prazo (nulo = sem restrição de início/fim)
    validade_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validade_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Limite de usos (nulo = ilimitado). `usos` conta os já consumidos.
    max_usos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now(),
    )
