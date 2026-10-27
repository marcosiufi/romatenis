"""Senhas, tokens e identidade de quem está logado.

Os tokens são JWT (HS256) e carregam `sv`, uma marca da senha atual: trocar a
senha invalida na hora todo token emitido antes — inclusive o refresh de sete
dias, que antes sobrevivia à troca.

Quatro tipos de token, distinguidos pelo campo `type`:

- **acesso** (sem `type`): 30 min, vai no `Authorization` de cada chamada;
- **refresh**: 7 dias, só serve para pedir um acesso novo;
- **2fa**: 10 min, prova que a senha do admin já foi conferida e só falta o
  código enviado por e-mail;
- **dispositivo**: 30 dias, dispensa o código no aparelho em que o admin já
  confirmou um código.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt as _bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

# tokenUrl aponta para o endpoint de login — usado apenas pelo Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_ALGORITHM = "HS256"

# O bcrypt só considera os primeiros 72 bytes. Versões novas da biblioteca
# recusam senhas maiores em vez de truncar em silêncio; cortamos na entrada.
SENHA_MAX = 72


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8")[:SENHA_MAX], _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8")[:SENHA_MAX], hashed.encode())
    except ValueError:
        # hash gravado num formato que a biblioteca não reconhece
        return False


def versao_senha(senha_hash: str) -> str:
    """Marca da senha atual, embutida nos tokens."""
    return hashlib.sha256(senha_hash.encode()).hexdigest()[:12]


def _emitir(payload: dict, validade: timedelta) -> str:
    agora = datetime.now(timezone.utc)
    return jwt.encode(
        {**payload, "iat": agora, "exp": agora + validade},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def _base(player, tipo: str | None) -> dict:
    dados = {"sub": str(player.id), "sv": versao_senha(player.senha_hash)}
    if tipo:
        dados["type"] = tipo
    return dados


def create_access_token(player) -> str:
    return _emitir(
        {**_base(player, None), "admin": bool(player.is_admin)},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(player) -> str:
    return _emitir(_base(player, "refresh"), timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def create_desafio_token(player) -> str:
    """Senha conferida; falta o código do segundo fator."""
    return _emitir(_base(player, "2fa"), timedelta(minutes=settings.CODIGO_LOGIN_MINUTOS))


def create_dispositivo_token(player) -> str:
    """Aparelho em que o admin já confirmou um código."""
    return _emitir(_base(player, "dispositivo"), timedelta(days=settings.DISPOSITIVO_CONFIAVEL_DIAS))


def decode_token(token: str, tipo: str | None = None) -> dict:
    """Payload do token, ou {} se inválido, expirado ou de outro tipo.

    O tipo é conferido sempre: um refresh não pode servir de acesso, nem um
    desafio de 2FA virar sessão.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return {}
    if payload.get("type") != tipo:
        return {}
    return payload


async def player_do_token(token: str, tipo: str | None, db: AsyncSession):
    """Jogador dono do token, ou None. Confere a marca da senha."""
    from app.models.player import Player  # evita import circular

    payload = decode_token(token, tipo)
    try:
        player_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    player = await db.get(Player, player_id)
    if player is None or payload.get("sv") != versao_senha(player.senha_hash):
        return None
    return player


async def get_current_player(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await player_do_token(token, None, db)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Entre de novo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return player


async def get_current_admin(
    player: Annotated["Player", Depends(get_current_player)],  # type: ignore[name-defined]
):
    if not player.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores")
    return player
