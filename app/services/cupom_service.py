"""
Lógica compartilhada de cupons de desconto.

Regra de negócio combinada com o admin:
  - O desconto do cupom SUBSTITUI o desconto de 5% do PIX (não acumula).
  - `usos` é incrementado na criação da cobrança, dentro da mesma transação.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cupom import Cupom

PIX_DESCONTO_PCT = 5  # desconto padrão do PIX à vista


class CupomError(ValueError):
    """Cupom inválido, expirado ou esgotado — mensagem já pronta para o usuário."""


async def buscar_cupom(db: AsyncSession, codigo: str) -> Cupom | None:
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    res = await db.execute(
        select(Cupom).where(func.upper(Cupom.codigo) == codigo)
    )
    return res.scalar_one_or_none()


async def validar_cupom(db: AsyncSession, codigo: str, agora: datetime | None = None) -> Cupom:
    """Retorna o cupom se estiver aplicável; senão levanta CupomError."""
    agora = agora or datetime.now(timezone.utc)
    cupom = await buscar_cupom(db, codigo)

    if cupom is None:
        raise CupomError("Cupom inválido.")
    if not cupom.ativo:
        raise CupomError("Este cupom não está mais ativo.")
    if cupom.validade_inicio and agora < cupom.validade_inicio:
        raise CupomError("Este cupom ainda não está válido.")
    if cupom.validade_fim and agora > cupom.validade_fim:
        raise CupomError("Este cupom expirou.")
    if cupom.max_usos is not None and cupom.usos >= cupom.max_usos:
        raise CupomError("Este cupom atingiu o limite de usos.")
    return cupom


def calcular_valor(valor_base: float, cupom: Cupom | None, pix: bool) -> dict:
    """
    Aplica o desconto e devolve o detalhamento.

    O cupom substitui o desconto do PIX. Sem cupom, o PIX à vista mantém os 5%.
    """
    valor_base = round(float(valor_base), 2)
    if cupom is not None:
        pct = cupom.percentual
        origem = "cupom"
    elif pix:
        pct = PIX_DESCONTO_PCT
        origem = "pix"
    else:
        pct = 0
        origem = None

    desconto = round(valor_base * pct / 100, 2)
    return {
        "valor_base": valor_base,
        "percentual": pct,
        "desconto": desconto,
        "valor_final": round(valor_base - desconto, 2),
        "origem": origem,
    }


async def registrar_uso(db: AsyncSession, cupom: Cupom) -> None:
    """Incrementa o contador de usos. Chamar na criação da cobrança."""
    cupom.usos = (cupom.usos or 0) + 1
    db.add(cupom)
