from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.player import NivelJogador


class PlayerBase(BaseModel):
    nome: str
    telefone: str
    email: EmailStr


class PlayerCreate(PlayerBase):
    senha: str


class PlayerUpdate(BaseModel):
    nome: str | None = None
    telefone: str | None = None
    email: EmailStr | None = None
    aceita_convites_sistema: bool | None = None


class PlayerOut(PlayerBase):
    model_config = {"from_attributes": True}

    id: int
    foto_url: str | None = None
    rating_atual: float
    nivel: NivelJogador
    partidas_computadas_rating: int
    pontos_ranking_temporada_atual: int
    aceita_convites_sistema: bool
    is_admin: bool
    data_cadastro: datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
