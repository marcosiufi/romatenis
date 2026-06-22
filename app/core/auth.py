from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

# tokenUrl aponta para o endpoint de login — usado apenas pelo Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(player_id: int, is_admin: bool) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": str(player_id), "admin": is_admin, "exp": expire},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def create_refresh_token(player_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    return jwt.encode(
        {"sub": str(player_id), "type": "refresh", "exp": expire},
        settings.SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return {}


async def get_current_player(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.models.player import Player  # evita import circular

    payload = _decode(token)
    if not payload or payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    player = await db.get(Player, int(payload["sub"]))
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jogador não encontrado")
    return player


async def get_current_admin(
    player: Annotated["Player", Depends(get_current_player)],  # type: ignore[name-defined]
):
    if not player.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores")
    return player


def decode_refresh_token(token: str) -> int | None:
    """Valida um refresh token e retorna o player_id, ou None se inválido."""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None
