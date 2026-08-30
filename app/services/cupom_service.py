"""
Lógica compartilhada de cupons de desconto.

Regra de negócio combinada com o admin:
  - O desconto do cupom SUBSTITUI o desconto de 5% do PIX (não acumula).
  - `usos` é incrementado na criação da cobrança, dentro da mesma transação.
"""
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
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
    """
    Incrementa o contador de usos. Chamar na criação da cobrança.

    O incremento é feito em SQL (`usos = usos + 1`) com o limite na cláusula
    WHERE: um read-modify-write em Python deixaria dois pedidos simultâneos
    lerem o mesmo valor e gravarem o mesmo número, estourando o `max_usos`.
    """
    resultado = await db.execute(
        update(Cupom)
        .where(
            Cupom.id == cupom.id,
            or_(Cupom.max_usos.is_(None), Cupom.usos < Cupom.max_usos),
        )
        .values(usos=Cupom.usos + 1)
    )
    if resultado.rowcount == 0:
        # Outro pedido consumiu a última vaga entre a validação e o commit
        raise CupomError("Este cupom atingiu o limite de usos.")
    # Mantém o objeto em memória coerente com o banco
    await db.refresh(cupom)


async def devolver_uso(db: AsyncSession, codigo: str) -> None:
    """Devolve uma vaga do cupom (pré-reserva que expirou sem pagamento)."""
    await db.execute(
        update(Cupom)
        .where(func.upper(Cupom.codigo) == codigo.upper(), Cupom.usos > 0)
        .values(usos=Cupom.usos - 1)
    )
