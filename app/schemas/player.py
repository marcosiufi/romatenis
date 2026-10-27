import re
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validators import cpf_valido, limpar_cpf
from app.models.player import NivelJogador, StatusJogador

# Mínimo combinado com o admin; o máximo é o que o bcrypt considera (72 bytes)
SENHA_MIN = 6
SENHA_MAX = 72


def normalizar_telefone(v: str) -> str:
    """Só dígitos, com DDD: '(16) 99123-4567' e '16991234567' viram a mesma coisa."""
    digitos = re.sub(r"\D", "", v or "")
    if not 10 <= len(digitos) <= 13:
        raise ValueError("Telefone inválido. Informe o DDD e o número.")
    return digitos


def normalizar_cpf_opcional(v: str | None) -> str | None:
    if v is None or not str(v).strip():
        return None
    if not cpf_valido(v):
        raise ValueError("CPF inválido.")
    return limpar_cpf(v)


def normalizar_uf(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip().upper()
    if len(v) != 2 or not v.isalpha():
        raise ValueError("Estado deve ser a sigla com 2 letras (ex: SP).")
    return v


class PlayerBase(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    telefone: str = Field(max_length=20)
    email: EmailStr = Field(max_length=255)

    @field_validator("telefone")
    @classmethod
    def _telefone(cls, v: str) -> str:
        return normalizar_telefone(v)

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Informe o nome.")
        return v


class _DadosPessoais(BaseModel):
    """Campos opcionais compartilhados por criação e edição, com os limites do banco."""

    cpf: str | None = Field(default=None, max_length=14)
    data_nascimento: date | None = None
    apelido: str | None = Field(default=None, max_length=50)
    # Endereço
    rua: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    complemento: str | None = Field(default=None, max_length=100)
    bairro: str | None = Field(default=None, max_length=100)
    cidade: str | None = Field(default=None, max_length=100)
    estado: str | None = Field(default=None, max_length=2)
    pais: str | None = Field(default=None, max_length=50)
    cep: str | None = Field(default=None, max_length=9)

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str | None) -> str | None:
        return normalizar_cpf_opcional(v)

    @field_validator("estado")
    @classmethod
    def _estado(cls, v: str | None) -> str | None:
        return normalizar_uf(v)


class PlayerCreate(PlayerBase, _DadosPessoais):
    senha: str = Field(min_length=SENHA_MIN, max_length=SENHA_MAX)
    pais: str | None = Field(default="Brasil", max_length=50)


class PlayerUpdate(_DadosPessoais):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    telefone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = Field(default=None, max_length=255)
    aceita_convites_sistema: bool | None = None

    @field_validator("telefone")
    @classmethod
    def _telefone(cls, v: str | None) -> str | None:
        return normalizar_telefone(v) if v else None


class PlayerRankingOut(BaseModel):
    """
    Visão pública de jogador — SEM dados pessoais.

    Usada na listagem do ranking e nos seletores de adversário, que são vistos
    por todos os membros. Nunca inclua CPF, endereço, telefone, e-mail ou
    nascimento aqui: para esses dados existe PlayerOut, restrito ao próprio
    jogador e ao admin.
    """

    model_config = {"from_attributes": True}

    id: int
    nome: str
    apelido: str | None = None
    foto_url: str | None = None
    rating_atual: float
    nivel: NivelJogador
    partidas_computadas_rating: int
    pontos_ranking_temporada_atual: int
    status: StatusJogador = StatusJogador.ATIVO


class PlayerOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    nome: str
    telefone: str
    email: str
    foto_url: str | None = None
    rating_atual: float
    nivel: NivelJogador
    partidas_computadas_rating: int
    pontos_ranking_temporada_atual: int
    aceita_convites_sistema: bool
    is_admin: bool
    data_cadastro: datetime
    # Dados pessoais
    cpf: str | None = None
    data_nascimento: date | None = None
    apelido: str | None = None
    # Endereço
    rua: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    estado: str | None = None
    pais: str | None = None
    cep: str | None = None
    # Status de atividade
    status: StatusJogador = StatusJogador.ATIVO
    data_inativacao: datetime | None = None
    # Contrato digital
    contrato_assinado: bool = False
    contrato_enviado_em: datetime | None = None
    contrato_assinado_em: datetime | None = None
    contrato_link_assinatura: str | None = None


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    senha: str = Field(min_length=1, max_length=SENHA_MAX)
    # Aparelho em que o admin já confirmou um código (ver app/core/auth.py)
    dispositivo_token: str | None = Field(default=None, max_length=2000)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Resposta do login.

    Jogador comum recebe os tokens direto. Admin sem aparelho confiável recebe
    `requer_codigo` e um `desafio` para trocar pelo código enviado por e-mail.
    """

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    requer_codigo: bool = False
    desafio: str | None = None
    enviado_para: str | None = None
    # Só na confirmação do código: guarda no aparelho para dispensar o próximo
    dispositivo_token: str | None = None


class CodigoLoginIn(BaseModel):
    desafio: str = Field(max_length=2000)
    codigo: str = Field(pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=2000)
