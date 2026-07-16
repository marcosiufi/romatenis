from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import inspect as sa_inspect

from app.models.match import LadoPartida, StatusPartida, TipoPartida


class MatchParticipantOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    player_id: int | None
    lado: LadoPartida
    rating_antes: float | None
    rating_depois: float | None
    pontos_atribuidos: int | None
    # Preenchidos apenas quando o participante é convidado (jogo avulso)
    convidado_id: int | None = None
    convidado_nome: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _resolver_nome_convidado(cls, data):
        """Deriva convidado_nome da relação, sem disparar lazy-load em async."""
        if isinstance(data, dict) or getattr(data, "convidado_id", None) is None:
            return data
        if "convidado" in sa_inspect(data).unloaded:
            return data
        convidado = data.convidado
        if convidado is None:
            return data
        return {
            "id": data.id,
            "player_id": data.player_id,
            "lado": data.lado,
            "rating_antes": data.rating_antes,
            "rating_depois": data.rating_depois,
            "pontos_atribuidos": data.pontos_atribuidos,
            "convidado_id": data.convidado_id,
            "convidado_nome": convidado.nome_exibicao,
        }


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
    avulso: bool = False
    participantes: list[MatchParticipantOut]


class PlacarSubmit(BaseModel):
    games_a: int = Field(ge=0, le=9)
    games_b: int = Field(ge=0, le=9)
    tiebreak_a: int | None = Field(default=None, ge=0)
    tiebreak_b: int | None = Field(default=None, ge=0)


class WOSubmit(BaseModel):
    lado_wo: str  # "A" ou "B"
