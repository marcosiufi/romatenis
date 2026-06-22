from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin, get_current_player, hash_password
from app.core.database import get_db
from app.models.player import Player
from app.schemas.player import PlayerCreate, PlayerOut, PlayerUpdate

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerOut])
async def list_players(db: Annotated[AsyncSession, Depends(get_db)]):
    """Ranking público — ordenado por pontos da temporada."""
    result = await db.execute(
        select(Player).order_by(Player.pontos_ranking_temporada_atual.desc())
    )
    return result.scalars().all()


@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def create_player(
    body: PlayerCreate,
    _admin: Annotated[Player, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin cria um jogador."""
    exists = await db.execute(select(Player).where(Player.email == body.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")

    player = Player(
        nome=body.nome,
        telefone=body.telefone,
        email=body.email,
        senha_hash=hash_password(body.senha),
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/me", response_model=PlayerOut)
async def get_me(player: Annotated[Player, Depends(get_current_player)]):
    return player


@router.patch("/me", response_model=PlayerOut)
async def update_me(
    body: PlayerUpdate,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(
    player_id: int,
    _current: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")
    return player


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: int,
    body: PlayerUpdate,
    _admin: Annotated[Player, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin atualiza qualquer jogador."""
    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player
