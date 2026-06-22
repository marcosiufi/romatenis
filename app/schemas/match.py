from datetime import datetime

from pydantic import BaseModel, Field

from app.models.match import LadoPartida, StatusPartida, TipoPartida


class MatchParticipantOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    player_id: int
    lado: LadoPartida
    rating_antes: float | None
    rating_depois: float | None
    pontos_atribuidos: int | None


class MatchOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tipo: TipoPartida
    status: StatusPartida
    data_hora: datetime
    duracao_minutos: int | None
    placar: dict | None
    lado_vencedor: str | None
    season_id: int | None
    participantes: list[MatchParticipantOut]


class PlacarSubmit(BaseModel):
    games_a: int = Field(ge=0, le=9)
    games_b: int = Field(ge=0, le=9)
    tiebreak_a: int | None = Field(default=None, ge=0)
    tiebreak_b: int | None = Field(default=None, ge=0)


class WOSubmit(BaseModel):
    lado_wo: str  # "A" ou "B"
