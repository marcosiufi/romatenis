from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.auth import get_current_admin, get_current_player
from app.core.database import get_db
from app.models.player import Player
from app.models.season import Season, StatusTemporada
from app.schemas.season import SeasonCreate, SeasonOut

router = APIRouter(prefix="/seasons", tags=["seasons"])


@router.get("", response_model=list[SeasonOut])
async def listar(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    result = await db.execute(select(Season).order_by(Season.id.desc()))
    return list(result.scalars().all())


@router.get("/ativa", response_model=SeasonOut | None)
async def ativa(
    _player: Player = Depends(get_current_player),
    db=Depends(get_db),
):
    result = await db.execute(
        select(Season).where(Season.status == StatusTemporada.ATIVA)
    )
    return result.scalar_one_or_none()


@router.post("", response_model=SeasonOut)
async def criar(
    body: SeasonCreate,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    existing = await db.execute(
        select(Season.id).where(Season.status == StatusTemporada.ATIVA)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(422, "Já existe uma temporada ativa. Encerre-a antes de criar outra.")

    if body.data_fim <= body.data_inicio:
        raise HTTPException(422, "data_fim deve ser posterior a data_inicio")

    season = Season(
        data_inicio=body.data_inicio,
        data_fim=body.data_fim,
        status=StatusTemporada.ATIVA,
    )
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season


@router.post("/{season_id}/encerrar", response_model=SeasonOut)
async def encerrar(
    season_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    season = await db.get(Season, season_id)
    if not season:
        raise HTTPException(404, "Temporada não encontrada")
    if season.status != StatusTemporada.ATIVA:
        raise HTTPException(422, f"Temporada já está '{season.status.value}'")

    # Snapshot do ranking final (apenas jogadores com ≥ 1 ponto)
    result = await db.execute(
        select(Player).order_by(Player.pontos_ranking_temporada_atual.desc())
    )
    players = list(result.scalars().all())

    season.ranking_final = [
        {
            "posicao": i + 1,
            "player_id": p.id,
            "nome": p.nome,
            "nivel": p.nivel.value,
            "pontos": p.pontos_ranking_temporada_atual,
            "rating": round(p.rating_atual, 1),
        }
        for i, p in enumerate(players)
        if p.pontos_ranking_temporada_atual > 0
    ]

    season.status = StatusTemporada.ENCERRADA

    # Zera pontos de todos os jogadores para a próxima temporada
    for p in players:
        p.pontos_ranking_temporada_atual = 0

    await db.commit()
    await db.refresh(season)
    return season
