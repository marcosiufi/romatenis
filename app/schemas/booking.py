from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.booking import StatusReserva, TipoReserva
from app.models.match import TipoPartida


class JogadorSlot(BaseModel):
    nome: str
    apelido: str | None = None
    lado: str  # "A" | "B"


class SlotDisponivel(BaseModel):
    data_hora_inicio: datetime
    data_hora_fim: datetime
    disponivel: bool
    # "ranking" | "ranking_ultima_hora" | "comercial_ultima_hora"
    # | "ocupado" | "passado" | "comercial" | "janela_morta"
    tipo_disponibilidade: str
    motivo_indisponibilidade: str | None = None
    jogadores: list[JogadorSlot] = []
    placar: dict | None = None
    lado_vencedor: str | None = None  # "A" | "B"
    status_partida: str | None = None  # "agendado" | "realizado" | "wo" | etc.


class BookingCreateRanking(BaseModel):
    data_hora: datetime
    tipo: TipoPartida
    lado_a: list[int]  # IDs (deve incluir o jogador que está fazendo a reserva)
    lado_b: list[int]  # IDs dos adversários

    @field_validator("data_hora")
    @classmethod
    def hora_cheia(cls, v: datetime) -> datetime:
        if v.minute != 0 or v.second != 0 or v.microsecond != 0:
            raise ValueError("O horário deve ser em hora cheia (ex: 17:00, 18:00)")
        return v


class BookingCreateLocacao(BaseModel):
    data_hora: datetime
    cliente_nome: str | None = None
    cliente_telefone: str | None = None

    @field_validator("data_hora")
    @classmethod
    def hora_cheia(cls, v: datetime) -> datetime:
        if v.minute != 0 or v.second != 0:
            raise ValueError("O horário deve ser em hora cheia")
        return v


class BookingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    data_hora_inicio: datetime
    data_hora_fim: datetime
    tipo: TipoReserva
    status: StatusReserva
    jogador_responsavel_id: int | None
    cliente_locacao_nome: str | None
    match_id: int | None
    valor: float | None
