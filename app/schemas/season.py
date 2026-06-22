from datetime import datetime

from pydantic import BaseModel

from app.models.season import StatusTemporada


class SeasonCreate(BaseModel):
    data_inicio: datetime
    data_fim: datetime


class SeasonOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    data_inicio: datetime
    data_fim: datetime
    status: StatusTemporada
    ranking_final: list | None
