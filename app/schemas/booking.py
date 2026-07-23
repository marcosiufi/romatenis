from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.validators import cpf_valido, limpar_cpf
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


# ── Jogo avulso ───────────────────────────────────────────────────────────────

class ConvidadoIn(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    cpf: str
    whatsapp: str = Field(min_length=8, max_length=20)
    data_nascimento: date
    apelido: str | None = Field(default=None, max_length=100)
    lado: Literal["A", "B"]

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v: str) -> str:
        if not cpf_valido(v):
            raise ValueError("CPF inválido")
        return limpar_cpf(v)

    @field_validator("whatsapp")
    @classmethod
    def limpar_whatsapp(cls, v: str) -> str:
        return "".join(c for c in v if c.isdigit())

    @field_validator("apelido")
    @classmethod
    def apelido_vazio_vira_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class BookingCreateJogoAvulso(BaseModel):
    data_hora: datetime
    tipo: TipoPartida
    metodo_pagamento: Literal["pix", "cartao"]
    cupom_codigo: str | None = None
    # Membros do ranking (inclui obrigatoriamente quem reserva, no lado A)
    membros_a: list[int] = []
    membros_b: list[int] = []
    # Jogadores de fora do ranking
    convidados: list[ConvidadoIn] = Field(min_length=1)

    @field_validator("data_hora")
    @classmethod
    def hora_cheia(cls, v: datetime) -> datetime:
        if v.minute != 0 or v.second != 0 or v.microsecond != 0:
            raise ValueError("O horário deve ser em hora cheia (ex: 17:00, 18:00)")
        return v


class JogoAvulsoOut(BaseModel):
    booking_id: int
    match_id: int
    valor: float
    pix_copia_cola: str | None = None
    pix_qrcode: str | None = None
    invoice_url: str | None = None
    msg: str


# ── Uso semanal ───────────────────────────────────────────────────────────────

class UsoTipoOut(BaseModel):
    usados: int
    limite: int
    restantes: int


class UsoSemanalOut(BaseModel):
    semana_inicio: date
    semana_fim: date
    simples: UsoTipoOut
    duplas: UsoTipoOut
