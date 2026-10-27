"""Login, renovação de sessão, segundo fator do admin e senhas.

Tudo aqui tem limite de tentativas (app/core/limite.py): login e código por IP
e por conta, redefinição por IP e por e-mail. Sem isso, a senha de qualquer
associado podia ser tentada sem parar, e o "esqueci a senha" servia para
encher a caixa de alguém de e-mails.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_desafio_token,
    create_dispositivo_token,
    create_refresh_token,
    get_current_player,
    hash_password,
    player_do_token,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.limite import exigir, por_ip
from app.models.player import Player
from app.schemas.player import (
    SENHA_MAX,
    SENHA_MIN,
    CodigoLoginIn,
    LoginRequest,
    LoginResponse,
    PlayerOut,
    RefreshRequest,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Tentativas de código por desafio: seis dígitos dão um milhão de combinações;
# cinco palpites em dez minutos não chegam perto.
CODIGO_TENTATIVAS_MAX = 5


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _mascarar_email(email: str) -> str:
    nome, _, dominio = email.partition("@")
    return f"{nome[:1]}***@{dominio}"


def _tokens(player: Player) -> dict:
    return {
        "access_token": create_access_token(player),
        "refresh_token": create_refresh_token(player),
    }


async def _enviar_codigo(player: Player, db: AsyncSession) -> None:
    from app.services import email_service

    codigo = f"{secrets.randbelow(10**6):06d}"
    player.codigo_login_hash = _hash(codigo)
    player.codigo_login_expira = datetime.now(timezone.utc) + timedelta(minutes=settings.CODIGO_LOGIN_MINUTOS)
    player.codigo_login_tentativas = 0
    await db.commit()
    if not settings.producao:
        # Ambiente local não tem SMTP: o código sai no log do container
        logger.warning("Código de login de %s (desenvolvimento): %s", player.email, codigo)
    try:
        await email_service.enviar_codigo_login(player.nome, player.email, codigo, settings.CODIGO_LOGIN_MINUTOS)
    except Exception as exc:  # noqa: BLE001 — qualquer falha de SMTP
        if settings.producao:
            # Melhor avisar do que deixar o admin esperando um e-mail que não
            # vem: a causa é o SMTP do servidor, e quem lê isto tem como corrigir
            logger.error("Falha ao enviar o código de login para %s: %s", player.email, exc)
            raise HTTPException(
                status_code=503,
                detail="Não foi possível enviar o código por e-mail. Confira a configuração "
                       "de e-mail do servidor (SMTP) e tente de novo.",
            )
        logger.info("Código não enviado por e-mail em desenvolvimento: %s", exc)


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(por_ip("login", 10, 60))])
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    exigir(f"login:conta:{body.email.lower()}", 20, 900)

    result = await db.execute(select(Player).where(Player.email == body.email))
    player = result.scalar_one_or_none()

    if player is None or not verify_password(body.senha, player.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
        )

    # Admin entra em duas etapas, salvo em aparelho onde já confirmou um
    # código. A regra vale para qualquer tela: o token de admin é o mesmo.
    if player.is_admin:
        confiavel = None
        if body.dispositivo_token:
            confiavel = await player_do_token(body.dispositivo_token, "dispositivo", db)
        if confiavel is None or confiavel.id != player.id:
            await _enviar_codigo(player, db)
            return LoginResponse(
                requer_codigo=True,
                desafio=create_desafio_token(player),
                enviado_para=_mascarar_email(player.email),
            )

    return LoginResponse(**_tokens(player))


@router.post("/login/codigo", response_model=LoginResponse, dependencies=[Depends(por_ip("login-codigo", 10, 300))])
async def confirmar_codigo(
    body: CodigoLoginIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await player_do_token(body.desafio, "2fa", db)
    if player is None:
        raise HTTPException(status_code=401, detail="Pedido expirado. Entre de novo com e-mail e senha.")

    agora = datetime.now(timezone.utc)
    if not player.codigo_login_hash or not player.codigo_login_expira or player.codigo_login_expira < agora:
        raise HTTPException(status_code=401, detail="Código expirado. Entre de novo para receber outro.")
    if player.codigo_login_tentativas >= CODIGO_TENTATIVAS_MAX:
        raise HTTPException(status_code=401, detail="Muitas tentativas erradas. Entre de novo para receber outro código.")

    if not secrets.compare_digest(_hash(body.codigo), player.codigo_login_hash):
        player.codigo_login_tentativas += 1
        await db.commit()
        raise HTTPException(status_code=401, detail="Código incorreto.")

    # Código é de uso único
    player.codigo_login_hash = None
    player.codigo_login_expira = None
    player.codigo_login_tentativas = 0
    await db.commit()

    return LoginResponse(**_tokens(player), dispositivo_token=create_dispositivo_token(player))


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(por_ip("refresh", 30, 60))])
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await player_do_token(body.refresh_token, "refresh", db)
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada. Entre de novo.")
    return TokenResponse(**_tokens(player))


@router.get("/me", response_model=PlayerOut)
async def me(player: Annotated[Player, Depends(get_current_player)]):
    return player


# ── Reset de senha ────────────────────────────────────────────────────────────

class EsqueciSenhaIn(BaseModel):
    email: EmailStr = Field(max_length=255)


class RedefinirSenhaIn(BaseModel):
    token: str = Field(max_length=200)
    nova_senha: str = Field(min_length=SENHA_MIN, max_length=SENHA_MAX)


@router.post("/esqueci-senha", status_code=200, dependencies=[Depends(por_ip("esqueci-senha", 5, 900))])
async def esqueci_senha(
    body: EsqueciSenhaIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Por e-mail também: senão dava para encher a caixa de alguém a partir de
    # vários IPs
    exigir(f"esqueci-senha:email:{body.email.lower()}", 3, 3600)

    player = (await db.execute(select(Player).where(Player.email == body.email))).scalar_one_or_none()
    if player is None:
        # Retorna 200 para não revelar se o e-mail existe
        return {"ok": True}

    token = secrets.token_urlsafe(32)
    # Só o hash vai ao banco: um vazamento da tabela não entrega links válidos
    player.reset_token = _hash(token)
    player.reset_token_expiracao = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    from app.services import email_service
    link = f"{settings.DOMAIN}/redefinir-senha?token={token}"
    await email_service.enviar_reset_senha(player.nome, player.email, link)

    return {"ok": True}


async def _player_do_reset(token: str, db: AsyncSession) -> Player:
    player = (await db.execute(select(Player).where(Player.reset_token == _hash(token)))).scalar_one_or_none()
    if not player or not player.reset_token_expiracao:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if player.reset_token_expiracao < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expirado. Solicite um novo link.")
    return player


@router.get("/validar-reset", dependencies=[Depends(por_ip("validar-reset", 20, 60))])
async def validar_reset(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await _player_do_reset(token, db)
    return {"ok": True, "nome": player.nome}


class AlterarSenhaIn(BaseModel):
    senha_atual: str = Field(max_length=SENHA_MAX)
    nova_senha: str = Field(min_length=SENHA_MIN, max_length=SENHA_MAX)


@router.post("/alterar-senha", response_model=TokenResponse)
async def alterar_senha(
    body: AlterarSenhaIn,
    player: Annotated[Player, Depends(get_current_player)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Troca a senha. Toda sessão anterior cai; a resposta traz tokens novos para esta."""
    if not verify_password(body.senha_atual, player.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    player.senha_hash = hash_password(body.nova_senha)
    await db.commit()
    return TokenResponse(**_tokens(player))


@router.post("/redefinir-senha", dependencies=[Depends(por_ip("redefinir-senha", 10, 60))])
async def redefinir_senha(
    body: RedefinirSenhaIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await _player_do_reset(body.token, db)
    player.senha_hash = hash_password(body.nova_senha)
    player.reset_token = None
    player.reset_token_expiracao = None
    await db.commit()

    return {"ok": True}
