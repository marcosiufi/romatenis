from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_player
from app.core.database import get_db
from app.models.player import Player
from app.schemas.match import MatchOut, PlacarSubmit, WOSubmit
from app.services.match_service import MatchError, MatchService

router = APIRouter(prefix="/matches", tags=["matches"])


def _svc(db=Depends(get_db)) -> MatchService:
    return MatchService(db)


@router.get("", response_model=list[MatchOut])
async def listar(
    player: Player = Depends(get_current_player),
    svc: MatchService = Depends(_svc),
):
    return await svc.listar_partidas(player)


@router.post("/{match_id}/placar", response_model=MatchOut)
async def submeter_placar(
    match_id: int,
    body: PlacarSubmit,
    player: Player = Depends(get_current_player),
    svc: MatchService = Depends(_svc),
):
    try:
        return await svc.submeter_placar(
            match_id, player, body.games_a, body.games_b, body.tiebreak_a, body.tiebreak_b
        )
    except MatchError as e:
        raise HTTPException(422, str(e))


@router.post("/{match_id}/wo", response_model=MatchOut)
async def registrar_wo(
    match_id: int,
    body: WOSubmit,
    player: Player = Depends(get_current_admin),
    svc: MatchService = Depends(_svc),
):
    try:
        return await svc.registrar_wo(match_id, body.lado_wo, player)
    except MatchError as e:
        raise HTTPException(422, str(e))


@router.post("/{match_id}/cancelar", response_model=MatchOut)
async def cancelar_sem_placar(
    match_id: int,
    player: Player = Depends(get_current_admin),
    svc: MatchService = Depends(_svc),
):
    try:
        return await svc.cancelar_sem_placar(match_id, player)
    except MatchError as e:
        raise HTTPException(422, str(e))


@router.post("/{match_id}/cancelar-jogador", response_model=MatchOut)
async def cancelar_por_jogador(
    match_id: int,
    player: Player = Depends(get_current_player),
    svc: MatchService = Depends(_svc),
):
    try:
        return await svc.cancelar_por_jogador(match_id, player)
    except MatchError as e:
        raise HTTPException(422, str(e))


@router.post("/recalcular-classificacao")
async def recalcular(
    _player: Player = Depends(get_current_admin),
    svc: MatchService = Depends(_svc),
):
    n = await svc.recalcular_classificacao()
    return {"jogadores_reclassificados": n}
