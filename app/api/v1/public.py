"""Endpoints públicos: disponibilidade de quadra, cadastro e reserva avulsa."""
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    get_current_player,
    hash_password,
)
from app.core.database import get_db
from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.configuracao import Configuracao
from app.models.payment import MetodoPagamento, Payment, StatusPagamento
from app.models.player import Player, StatusJogador
from app.models.slot_ranking import SlotRanking
from app.schemas.player import TokenResponse

router = APIRouter(prefix="/public", tags=["public"])
FUSO_BR = ZoneInfo("America/Sao_Paulo")
_HORA_ABERTURA = 7
_HORA_FECHAMENTO = 22


# ── Disponibilidade ───────────────────────────────────────────────────────────

class SlotOut(BaseModel):
    hora_inicio: str
    hora_fim: str
    status: Literal["disponivel", "ocupado", "bloqueado_ranking"]
    motivo: str | None = None


class DisponibilidadeOut(BaseModel):
    data: str
    preco_hora: float
    slots: list[SlotOut]


@router.get("/disponibilidade", response_model=DisponibilidadeOut)
async def disponibilidade(
    data: date = Query(..., description="Data desejada (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    agora_br = datetime.now(FUSO_BR)
    if data < agora_br.date():
        raise HTTPException(status_code=400, detail="Data não pode ser no passado.")

    cfg = await Configuracao.get(db)
    preco = float(cfg.preco_locacao_hora)

    dia_semana = data.weekday()  # 0=segunda, 6=domingo
    slots_ranking = (
        await db.execute(
            select(SlotRanking).where(
                SlotRanking.dia_semana == dia_semana,
                SlotRanking.ativo.is_(True),
            )
        )
    ).scalars().all()

    inicio_dia = datetime.combine(data, time(0, 0), tzinfo=FUSO_BR)
    fim_dia = inicio_dia + timedelta(days=1)
    bookings_dia = (
        await db.execute(
            select(Booking).where(
                and_(
                    Booking.status == StatusReserva.CONFIRMADA,
                    Booking.data_hora_inicio >= inicio_dia,
                    Booking.data_hora_inicio < fim_dia,
                )
            )
        )
    ).scalars().all()

    def _ocupado(hora: int) -> bool:
        s = datetime.combine(data, time(hora, 0), tzinfo=FUSO_BR)
        f = s + timedelta(hours=1)
        return any(b.data_hora_inicio < f and b.data_hora_fim > s for b in bookings_dia)

    def _ranking(hora: int) -> bool:
        t = time(hora, 0)
        return any(s.hora_inicio <= t < s.hora_fim for s in slots_ranking)

    slots_out: list[SlotOut] = []
    for hora in range(_HORA_ABERTURA, _HORA_FECHAMENTO):
        slot_ini = datetime.combine(data, time(hora, 0), tzinfo=FUSO_BR)
        h_fmt = f"{hora:02d}:00"
        hf_fmt = f"{hora + 1:02d}:00"

        if _ocupado(hora):
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="ocupado", motivo="Horário já reservado"))
        elif _ranking(hora):
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="bloqueado_ranking", motivo="Reservado para o ranking"))
        else:
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="disponivel"))

    return DisponibilidadeOut(data=str(data), preco_hora=preco, slots=slots_out)


# ── Cadastro público ──────────────────────────────────────────────────────────

class CadastroPublicoIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    telefone: str
    cpf: str | None = None
    data_nascimento: date | None = None

    @field_validator("senha")
    @classmethod
    def senha_minima(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        return v

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome é obrigatório.")
        return v


@router.post("/cadastro", response_model=TokenResponse, status_code=201)
async def cadastro_publico(
    body: CadastroPublicoIn,
    db: AsyncSession = Depends(get_db),
):
    if await db.scalar(select(Player).where(Player.email == body.email)):
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    if await db.scalar(select(Player).where(Player.telefone == body.telefone)):
        raise HTTPException(status_code=409, detail="Telefone já cadastrado.")

    player = Player(
        nome=body.nome.strip(),
        email=body.email,
        telefone=body.telefone,
        senha_hash=hash_password(body.senha),
        cpf=body.cpf,
        data_nascimento=body.data_nascimento,
        status=StatusJogador.INATIVO.value,
        is_admin=False,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)

    return TokenResponse(
        access_token=create_access_token(player.id, player.is_admin),
        refresh_token=create_refresh_token(player.id),
    )


# ── Reserva avulsa ────────────────────────────────────────────────────────────

class ReservaIn(BaseModel):
    data: date
    hora_inicio: str   # "HH:00"
    tipo: Literal["simples", "duplas"] = "simples"
    metodo_pagamento: Literal["pix", "cartao"] = "pix"


class PixOut(BaseModel):
    booking_id: int
    valor: float
    pix_copia_cola: str | None = None
    pix_qrcode: str | None = None
    invoice_url: str | None = None
    asaas_payment_id: str | None = None
    msg: str


@router.post("/reserva", response_model=PixOut, status_code=201)
async def reservar(
    body: ReservaIn,
    player: Annotated[Player, Depends(get_current_player)],
    db: AsyncSession = Depends(get_db),
):
    agora_br = datetime.now(FUSO_BR)
    if body.data < agora_br.date():
        raise HTTPException(status_code=400, detail="Data não pode ser no passado.")

    try:
        hora = int(body.hora_inicio.split(":")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail="Hora inválida. Use o formato HH:00.")

    if hora < _HORA_ABERTURA or hora >= _HORA_FECHAMENTO:
        raise HTTPException(status_code=400, detail="Horário fora do funcionamento.")

    slot_ini = datetime.combine(body.data, time(hora, 0), tzinfo=FUSO_BR)
    slot_fim = slot_ini + timedelta(hours=1)

    # Verificar disponibilidade
    dia_semana = body.data.weekday()
    slots_ranking = (
        await db.execute(
            select(SlotRanking).where(
                SlotRanking.dia_semana == dia_semana,
                SlotRanking.ativo.is_(True),
            )
        )
    ).scalars().all()

    existente = await db.scalar(
        select(Booking).where(
            and_(
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio < slot_fim,
                Booking.data_hora_fim > slot_ini,
            )
        )
    )
    if existente:
        raise HTTPException(status_code=409, detail="Horário já reservado.")

    t = time(hora, 0)
    is_ranking = any(s.hora_inicio <= t < s.hora_fim for s in slots_ranking)
    if is_ranking:
        raise HTTPException(
            status_code=409,
            detail="Este horário está reservado para o ranking e não pode ser alugado.",
        )

    cfg = await Configuracao.get(db)
    valor = float(cfg.preco_locacao_hora)

    booking = Booking(
        data_hora_inicio=slot_ini,
        data_hora_fim=slot_fim,
        tipo=TipoReserva.LOCACAO_AVULSA,
        status=StatusReserva.CONFIRMADA,
        jogador_responsavel_id=player.id,
        valor=valor,
    )
    db.add(booking)
    await db.flush()

    # Tentar criar cobrança Asaas
    pix_copia_cola = None
    pix_qrcode = None
    invoice_url = None
    asaas_payment_id = None
    msg = "Reserva confirmada! Entre em contato para acertar o pagamento."

    try:
        from app.services.asaas_client import AsaasClient, AsaasError
        asaas = AsaasClient()
        customer_id = player.asaas_customer_id
        if not customer_id:
            customer_id = await asaas.get_or_create_customer(
                nome=player.nome,
                email=player.email,
                telefone=player.telefone,
                cpf=player.cpf,
            )
            player.asaas_customer_id = customer_id

        billing_type = "CREDIT_CARD" if body.metodo_pagamento == "cartao" else "PIX"
        data_venc = body.data.isoformat()
        descricao = f"Locação Roma Tênis — {body.data.strftime('%d/%m/%Y')} {hora:02d}h"
        charge = await asaas.criar_cobranca(
            customer_id=customer_id,
            valor=valor,
            billing_type=billing_type,
            due_date=data_venc,
            descricao=descricao,
        )
        asaas_payment_id = charge.get("id")

        if body.metodo_pagamento == "cartao":
            invoice_url = charge.get("invoiceUrl")
            msg = "Reserva confirmada! Clique no botão para pagar com cartão."
        else:
            if asaas_payment_id:
                qr = await asaas.get_pix_qrcode(asaas_payment_id)
                pix_copia_cola = qr.get("payload")
                pix_qrcode = qr.get("encodedImage")
            msg = "Reserva confirmada! Pague via PIX abaixo para garantir o horário."

        payment = Payment(
            booking_id=booking.id,
            valor=valor,
            metodo=MetodoPagamento.CARTAO if body.metodo_pagamento == "cartao" else MetodoPagamento.PIX,
            status=StatusPagamento.PENDENTE,
            gateway_id=asaas_payment_id,
        )
        db.add(payment)
    except Exception:
        pass  # Se Asaas falhar, mantém a reserva sem pagamento online

    await db.commit()

    return PixOut(
        booking_id=booking.id,
        valor=valor,
        pix_copia_cola=pix_copia_cola,
        pix_qrcode=pix_qrcode,
        invoice_url=invoice_url,
        asaas_payment_id=asaas_payment_id,
        msg=msg,
    )
