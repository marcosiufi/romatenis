from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Convidado(Base):
    """Jogador de fora do ranking, convidado por um membro para um jogo avulso."""

    __tablename__ = "convidados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=False, index=True)
    whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=False)
    apelido: Mapped[str | None] = mapped_column(String(100), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now(),
    )

    participacoes: Mapped[list["MatchParticipant"]] = relationship(back_populates="convidado")

    @property
    def nome_exibicao(self) -> str:
        if self.apelido:
            return self.apelido
        partes = self.nome.strip().split()
        return f"{partes[0]} {partes[-1]}" if len(partes) > 1 else self.nome
