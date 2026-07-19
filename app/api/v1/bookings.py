from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin, get_current_player
from app.core.database import get_db
from app.models.feriado import Feriado
from app.models.player import Player
from app.schemas.booking import (
    BookingCreateJogoAvulso,
    BookingCreateLocacao,
    BookingCreateRanking,
    BookingOut,
    JogoAvulsoOut,
    SlotDisponivel,
    UsoSemanalOut,
)
from app.services.booking_service import (
    BookingError,
    BookingService,
    ReservasDesabilitadasError,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

_DB = Annotated[AsyncSession, Depends(get_db)]
_Player = Annotated[Player, Depends(get_current_player)]
_Admin = Annotated[Player, Depends(get_current_admin)]


def _booking_error(e: BookingError) -> HTTPException:
    # Reservas desligadas no painel não são erro de validação do pedido: 403
    # deixa o app distinguir "ainda não abrimos" de "seu pedido é inválido".
    if isinstance(e, ReservasDesabilitadasError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ── Slots disponíveis ─────────────────────────────────────────────────────────

@router.get("/slots", response_model=list[SlotDisponivel])
async def listar_slots(
    data: date,
    tipo: str,
    player: _Player,
    db: _DB,
):
    """Retorna os slots de 1h para a data informada (horário de Brasília)."""
    from app.models.match import TipoPartida
    try:
        tipo_enum = TipoPartida(tipo)
    except ValueError:
        raise HTTPException(400, detail="tipo deve ser 'simples' ou 'duplas'")
    return await BookingService(db).listar_slots(data, player, tipo_enum)


# ── Reservas do jogador ───────────────────────────────────────────────────────

@router.get("", response_model=list[BookingOut])
async def listar_reservas(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    player: _Player = None,
    db: _DB = None,
):
    return await BookingService(db).listar_reservas(player, data_inicio, data_fim)


# ── Criar reserva de ranking ──────────────────────────────────────────────────

@router.post("/ranking", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def criar_reserva_ranking(body: BookingCreateRanking, player: _Player, db: _DB):
    try:
        booking, _ = await BookingService(db).criar_reserva_ranking(
            player=player,
            data_hora=body.data_hora,
            tipo=body.tipo,
            lado_a=body.lado_a,
            lado_b=body.lado_b,
        )
    except BookingError as e:
        raise _booking_error(e)
    return booking


# ── Uso semanal de jogos ──────────────────────────────────────────────────────

@router.get("/uso-semanal", response_model=UsoSemanalOut)
async def uso_semanal(player: _Player, db: _DB):
    """Cota de jogos consumida e restante na semana corrente (seg–dom)."""
    return await BookingService(db).uso_semanal(player)


# ── Criar jogo avulso ─────────────────────────────────────────────────────────

@router.post("/jogo-avulso", response_model=JogoAvulsoOut, status_code=status.HTTP_201_CREATED)
async def criar_jogo_avulso(body: BookingCreateJogoAvulso, player: _Player, db: _DB):
    try:
        return await BookingService(db).criar_jogo_avulso(
            player=player,
            data_hora=body.data_hora,
            tipo=body.tipo,
            membros_a=body.membros_a,
            membros_b=body.membros_b,
            convidados=body.convidados,
            metodo_pagamento=body.metodo_pagamento,
        )
    except BookingError as e:
        raise _booking_error(e)


# ── Criar locação avulsa ──────────────────────────────────────────────────────

@router.post("/locacao", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def criar_locacao_avulsa(body: BookingCreateLocacao, player: _Player, db: _DB):
    try:
        booking = await BookingService(db).criar_locacao_avulsa(
            data_hora=body.data_hora,
            player=player,
            nome_externo=body.cliente_nome,
            telefone_externo=body.cliente_telefone,
        )
    except BookingError as e:
        raise _booking_error(e)
    return booking


# ── Cancelar reserva ─────────────────────────────────────────────────────────

@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar_reserva(booking_id: int, player: _Player, db: _DB):
    try:
        await BookingService(db).cancelar_reserva(booking_id, player)
    except BookingError as e:
        raise _booking_error(e)


# ── Feriados (admin) ──────────────────────────────────────────────────────────

@router.get("/feriados", tags=["admin"])
async def listar_feriados(db: _DB):
    from sqlalchemy import select
    result = await db.execute(select(Feriado).order_by(Feriado.data))
    return result.scalars().all()


@router.post("/feriados", status_code=status.HTTP_201_CREATED, tags=["admin"])
async def criar_feriado(
    data: date,
    descricao: str,
    recorrente: bool = False,
    _admin: _Admin = None,
    db: _DB = None,
):
    feriado = Feriado(data=data, descricao=descricao, recorrente=recorrente)
    db.add(feriado)
    await db.commit()
    await db.refresh(feriado)
    return feriado


@router.delete("/feriados/{feriado_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["admin"])
async def deletar_feriado(feriado_id: int, _admin: _Admin, db: _DB):
    feriado = await db.get(Feriado, feriado_id)
    if feriado is None:
        raise HTTPException(404, "Feriado não encontrado")
    await db.delete(feriado)
    await db.commit()
