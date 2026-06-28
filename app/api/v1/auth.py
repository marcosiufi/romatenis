import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_player,
    hash_password,
    verify_password,
)
from app.core.config import settings
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


# ── Reset de senha ────────────────────────────────────────────────────────────

class EsqueciSenhaIn(BaseModel):
    email: EmailStr


class RedefinirSenhaIn(BaseModel):
    token: str
    nova_senha: str


@router.post("/esqueci-senha", status_code=200)
async def esqueci_senha(
    body: EsqueciSenhaIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = (await db.execute(select(Player).where(Player.email == body.email))).scalar_one_or_none()
    if player is None:
        # Retorna 200 para não revelar se o e-mail existe
        return {"ok": True}

    token = secrets.token_urlsafe(32)
    player.reset_token = token
    player.reset_token_expiracao = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    from app.services import email_service
    link = f"{settings.DOMAIN}/redefinir-senha?token={token}"
    await email_service.enviar_reset_senha(player.nome, player.email, link)

    return {"ok": True}


@router.get("/validar-reset")
async def validar_reset(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = (await db.execute(select(Player).where(Player.reset_token == token))).scalar_one_or_none()
    if not player or not player.reset_token_expiracao:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if player.reset_token_expiracao.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expirado. Solicite um novo link.")
    return {"ok": True, "nome": player.nome}


class AlterarSenhaIn(BaseModel):
    senha_atual: str
    nova_senha: str


@router.post("/alterar-senha")
async def alterar_senha(
    body: AlterarSenhaIn,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not verify_password(body.senha_atual, player.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    if len(body.nova_senha) < 6:
        raise HTTPException(status_code=422, detail="A nova senha deve ter pelo menos 6 caracteres.")
    player.senha_hash = hash_password(body.nova_senha)
    await db.commit()
    return {"ok": True}


@router.post("/redefinir-senha")
async def redefinir_senha(
    body: RedefinirSenhaIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if len(body.nova_senha) < 6:
        raise HTTPException(status_code=422, detail="A senha deve ter pelo menos 6 caracteres.")

    player = (await db.execute(select(Player).where(Player.reset_token == body.token))).scalar_one_or_none()
    if not player or not player.reset_token_expiracao:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if player.reset_token_expiracao.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expirado. Solicite um novo link.")

    player.senha_hash = hash_password(body.nova_senha)
    player.reset_token = None
    player.reset_token_expiracao = None
    await db.commit()

    return {"ok": True}
