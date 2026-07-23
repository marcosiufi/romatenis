from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CupomBase(BaseModel):
    codigo: str = Field(min_length=2, max_length=40)
    percentual: int = Field(ge=1, le=100)
    descricao: str | None = Field(default=None, max_length=200)
    validade_inicio: datetime | None = None
    validade_fim: datetime | None = None
    max_usos: int | None = Field(default=None, ge=1)
    ativo: bool = True

    @field_validator("codigo")
    @classmethod
    def normaliza_codigo(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("O código deve conter apenas letras, números, hífen ou underline.")
        return v


class CupomCreate(CupomBase):
    pass


class CupomUpdate(BaseModel):
    percentual: int | None = Field(default=None, ge=1, le=100)
    descricao: str | None = Field(default=None, max_length=200)
    validade_inicio: datetime | None = None
    validade_fim: datetime | None = None
    max_usos: int | None = Field(default=None, ge=1)
    ativo: bool | None = None


class CupomOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    codigo: str
    percentual: int
    descricao: str | None
    validade_inicio: datetime | None
    validade_fim: datetime | None
    max_usos: int | None
    usos: int
    ativo: bool
    criado_em: datetime


class CupomValidarIn(BaseModel):
    codigo: str


class CupomValidarOut(BaseModel):
    valido: bool
    codigo: str | None = None
    percentual: int | None = None
    descricao: str | None = None
    msg: str | None = None
