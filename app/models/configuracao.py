from sqlalchemy import Numeric, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Configuracao(Base):
    __tablename__ = "configuracoes"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Preços totais por plano (R$)
    preco_mensal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=89.90)
    preco_trimestral: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=239.90)
    preco_semestral: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=449.90)
    preco_anual: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=839.90)

    # Locação avulsa
    preco_locacao_hora: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=120.00)

    @classmethod
    async def get(cls, db: AsyncSession) -> "Configuracao":
        """Retorna a única linha de config, criando com defaults se não existir."""
        row = (await db.execute(select(cls).where(cls.id == 1))).scalar_one_or_none()
        if row is None:
            row = cls(id=1)
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row
