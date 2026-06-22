from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_player,
    verify_password,
)
from app.core.database import get_db
from app.models.player import Player
from app.schemas.player import LoginRequest, PlayerOut, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Player).where(Player.email == body.email))
    player = result.scalar_one_or_none()

    if player is None or not verify_password(body.senha, player.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
        )

    return TokenResponse(
        access_token=create_access_token(player.id, player.is_admin),
        refresh_token=create_refresh_token(player.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player_id = decode_refresh_token(body.refresh_token)
    if player_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")

    player = await db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jogador não encontrado")

    return TokenResponse(
        access_token=create_access_token(player.id, player.is_admin),
        refresh_token=create_refresh_token(player.id),
    )


@router.get("/me", response_model=PlayerOut)
async def me(player: Annotated[Player, Depends(get_current_player)]):
    return player
