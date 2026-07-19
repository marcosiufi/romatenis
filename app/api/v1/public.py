"""Endpoints públicos: disponibilidade de quadra, cadastro e reserva avulsa."""
import re
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import and_, or_, select
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
from app.models.horario_especial import HorarioEspecial
from app.models.horario_dia_semana import HorarioDiaSemana
from app.models.payment import MetodoPagamento, Payment, StatusPagamento
from app.models.player import Player, StatusJogador
from app.models.season import Season, StatusTemporada
from app.models.slot_ranking import SlotRanking
from app.schemas.player import TokenResponse

router = APIRouter(prefix="/public", tags=["public"])
FUSO_BR = ZoneInfo("America/Sao_Paulo")


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

    # Horário base: config por dia da semana > global
    dia_cfg = await db.scalar(
        select(HorarioDiaSemana).where(HorarioDiaSemana.dia_semana == data.weekday())
    )
    if dia_cfg and not dia_cfg.aberto:
        return DisponibilidadeOut(data=str(data), preco_hora=preco, slots=[])
    hora_abertura = dia_cfg.hora_abertura if dia_cfg else cfg.hora_abertura
    hora_fechamento = dia_cfg.hora_fechamento if dia_cfg else cfg.hora_fechamento

    # HorarioEspecial (data específica) tem prioridade máxima
    especial = await db.scalar(select(HorarioEspecial).where(HorarioEspecial.data == data))
    if especial:
        if especial.fechado:
            return DisponibilidadeOut(
                data=str(data),
                preco_hora=preco,
                slots=[
                    SlotOut(
                        hora_inicio=f"{h:02d}:00",
                        hora_fim=f"{h + 1:02d}:00",
                        status="ocupado",
                        motivo=f"Quadra fechada — {especial.descricao}",
                    )
                    for h in range(hora_abertura, hora_fechamento)
                ],
            )
        if especial.hora_abertura is not None:
            hora_abertura = especial.hora_abertura
        if especial.hora_fechamento is not None:
            hora_fechamento = especial.hora_fechamento

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
    cutoff_pag = agora_br - timedelta(minutes=10)
    bookings_dia = (
        await db.execute(
            select(Booking).where(
                and_(
                    or_(
                        Booking.status == StatusReserva.CONFIRMADA,
                        and_(
                            Booking.status == StatusReserva.AGUARDANDO_PAGAMENTO,
                            Booking.criado_em >= cutoff_pag,
                        ),
                    ),
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

    horas_libera = cfg.locacao_libera_slot_ranking_horas
    libera_ranking = timedelta(hours=horas_libera)

    slots_out: list[SlotOut] = []
    for hora in range(hora_abertura, hora_fechamento):
        slot_ini = datetime.combine(data, time(hora, 0), tzinfo=FUSO_BR)
        h_fmt = f"{hora:02d}:00"
        hf_fmt = f"{hora + 1:02d}:00"

        if slot_ini < agora_br:
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="ocupado", motivo="Horário já passou"))
        elif _ocupado(hora):
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="ocupado", motivo="Horário já reservado"))
        elif _ranking(hora) and agora_br < slot_ini - libera_ranking:
            slots_out.append(SlotOut(
                hora_inicio=h_fmt, hora_fim=hf_fmt, status="bloqueado_ranking",
                motivo=f"Reservado para o ranking — disponível {horas_libera}h antes",
            ))
        else:
            slots_out.append(SlotOut(hora_inicio=h_fmt, hora_fim=hf_fmt, status="disponivel"))

    return DisponibilidadeOut(data=str(data), preco_hora=preco, slots=slots_out)


# ── Cadastro público ──────────────────────────────────────────────────────────

class CadastroPublicoIn(BaseModel):
    nome: str
    apelido: str
    email: EmailStr
    senha: str
    telefone: str
    cpf: str
    data_nascimento: date
    # endereço
    cep: str
    rua: str
    numero: str
    bairro: str
    cidade: str
    estado: str
    pais: str = "Brasil"
    complemento: str | None = None

    @field_validator("cpf")
    @classmethod
    def cpf_valido(cls, v: str) -> str:
        cpf = re.sub(r"\D", "", v)
        if len(cpf) != 11 or len(set(cpf)) == 1:
            raise ValueError("CPF inválido.")
        soma = sum(int(cpf[j]) * (10 - j) for j in range(9))
        d1 = 0 if soma % 11 < 2 else 11 - soma % 11
        if d1 != int(cpf[9]):
            raise ValueError("CPF inválido.")
        soma = sum(int(cpf[j]) * (11 - j) for j in range(10))
        d2 = 0 if soma % 11 < 2 else 11 - soma % 11
        if d2 != int(cpf[10]):
            raise ValueError("CPF inválido.")
        return cpf

    @field_validator("cep")
    @classmethod
    def cep_valido(cls, v: str) -> str:
        cep = re.sub(r"\D", "", v)
        if len(cep) != 8:
            raise ValueError("CEP inválido.")
        return cep

    @field_validator("estado")
    @classmethod
    def estado_sigla(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2:
            raise ValueError("Estado deve ser a sigla com 2 letras (ex: SP).")
        return v

    @field_validator("senha")
    @classmethod
    def senha_minima(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        return v

    @field_validator("nome", "apelido", "rua", "numero", "bairro", "cidade")
    @classmethod
    def nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Campo obrigatório.")
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
    if await db.scalar(select(Player).where(Player.cpf == body.cpf)):
        raise HTTPException(status_code=409, detail="CPF já cadastrado.")

    player = Player(
        nome=body.nome.strip(),
        apelido=body.apelido.strip(),
        email=body.email,
        telefone=body.telefone,
        senha_hash=hash_password(body.senha),
        cpf=body.cpf,
        data_nascimento=body.data_nascimento,
        cep=body.cep,
        rua=body.rua.strip(),
        numero=body.numero.strip(),
        complemento=body.complemento.strip() if body.complemento else None,
        bairro=body.bairro.strip(),
        cidade=body.cidade.strip(),
        estado=body.estado,
        pais=body.pais or "Brasil",
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
    num_horas: int = 1

    @field_validator("num_horas")
    @classmethod
    def num_horas_valido(cls, v: int) -> int:
        if not 1 <= v <= 4:
            raise ValueError("Número de horas deve ser entre 1 e 4.")
        return v


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

    cfg = await Configuracao.get(db)
    if not cfg.reservas_ativas:
        raise HTTPException(status_code=403, detail=cfg.msg_reservas_desabilitado)
    valor = float(cfg.preco_locacao_hora) * body.num_horas

    # Horário base: config por dia da semana > global
    dia_cfg_r = await db.scalar(
        select(HorarioDiaSemana).where(HorarioDiaSemana.dia_semana == body.data.weekday())
    )
    if dia_cfg_r and not dia_cfg_r.aberto:
        raise HTTPException(status_code=409, detail="A quadra está fechada neste dia.")
    hora_ab = dia_cfg_r.hora_abertura if dia_cfg_r else cfg.hora_abertura
    hora_fe = dia_cfg_r.hora_fechamento if dia_cfg_r else cfg.hora_fechamento

    especial_r = await db.scalar(select(HorarioEspecial).where(HorarioEspecial.data == body.data))
    if especial_r and especial_r.fechado:
        raise HTTPException(status_code=409, detail=f"A quadra está fechada nesta data — {especial_r.descricao}.")
    if especial_r and especial_r.hora_abertura is not None:
        hora_ab = especial_r.hora_abertura
    if especial_r and especial_r.hora_fechamento is not None:
        hora_fe = especial_r.hora_fechamento
    if hora < hora_ab or hora >= hora_fe:
        raise HTTPException(status_code=400, detail="Horário fora do funcionamento.")

    slot_ini = datetime.combine(body.data, time(hora, 0), tzinfo=FUSO_BR)
    if body.data == agora_br.date() and slot_ini < agora_br:
        raise HTTPException(status_code=400, detail="Este horário já passou.")
    slot_fim = slot_ini + timedelta(hours=body.num_horas)
    if hora + body.num_horas > hora_fe:
        raise HTTPException(status_code=400, detail=f"A duração selecionada excede o fechamento da quadra ({hora_fe:02d}:00).")

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

    cutoff_pag_r = agora_br - timedelta(minutes=10)
    existente = await db.scalar(
        select(Booking).where(
            and_(
                or_(
                    Booking.status == StatusReserva.CONFIRMADA,
                    and_(
                        Booking.status == StatusReserva.AGUARDANDO_PAGAMENTO,
                        Booking.criado_em >= cutoff_pag_r,
                    ),
                ),
                Booking.data_hora_inicio < slot_fim,
                Booking.data_hora_fim > slot_ini,
            )
        )
    )
    if existente:
        raise HTTPException(status_code=409, detail="Horário já reservado.")

    for h in range(hora, hora + body.num_horas):
        t_h = time(h, 0)
        slot_h = datetime.combine(body.data, t_h, tzinfo=FUSO_BR)
        horas_libera_r = cfg.locacao_libera_slot_ranking_horas
        if any(s.hora_inicio <= t_h < s.hora_fim for s in slots_ranking) and agora_br < slot_h - timedelta(hours=horas_libera_r):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"O horário das {h:02d}:00 está reservado para o ranking e só pode "
                    f"ser alugado nas {horas_libera_r} horas anteriores ao jogo."
                ),
            )

    booking = Booking(
        data_hora_inicio=slot_ini,
        data_hora_fim=slot_fim,
        tipo=TipoReserva.LOCACAO_AVULSA,
        status=StatusReserva.AGUARDANDO_PAGAMENTO,
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
    msg = "Pré-reserva criada! Entre em contato para confirmar o pagamento e garantir o horário."

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
        descricao = f"Locação Roma Tênis — {body.data.strftime('%d/%m/%Y')} {hora:02d}h às {(hora + body.num_horas):02d}h"
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
            msg = "Pré-reserva criada! Pague com cartão no link abaixo. O horário será confirmado após a aprovação do pagamento."
        else:
            if asaas_payment_id:
                qr = await asaas.get_pix_qrcode(asaas_payment_id)
                pix_copia_cola = qr.get("payload")
                pix_qrcode = qr.get("encodedImage")
            msg = "Pré-reserva criada! Pague via PIX abaixo. O horário será confirmado assim que o pagamento for identificado."

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


# ── Dados públicos da empresa ────────────────────────────────────────────────

@router.get("/empresa")
async def empresa_publica(db: AsyncSession = Depends(get_db)):
    cfg = await Configuracao.get(db)
    comp = f", {cfg.end_complemento}" if cfg.end_complemento else ""
    endereco = (
        f"{cfg.end_logradouro}, {cfg.end_numero}{comp}\n"
        f"{cfg.end_bairro}, {cfg.end_cidade}-{cfg.end_estado} · CEP {cfg.end_cep}"
    )
    return {
        "razao_social":      cfg.razao_social,
        "nome_fantasia":     cfg.nome_fantasia,
        "cnpj":              cfg.cnpj,
        "endereco":          endereco,
        "whatsapp":          cfg.whatsapp,
        "instagram":         cfg.instagram,
        "email_contato":     cfg.email_contato,
        "preco_locacao_hora": float(cfg.preco_locacao_hora),
        "preco_jogo_avulso":  float(cfg.preco_jogo_avulso),
        # Estado comercial: o front avisa antes de o usuário tentar contratar
        "contratacao_planos_ativa":  cfg.contratacao_planos_ativa,
        "reservas_ativas":           cfg.reservas_ativas,
        "msg_planos_desabilitado":   cfg.msg_planos_desabilitado,
        "msg_reservas_desabilitado": cfg.msg_reservas_desabilitado,
    }


# ── Horários de funcionamento (público) ───────────────────────────────────────

@router.get("/temporadas")
async def temporadas_publico(db: AsyncSession = Depends(get_db)):
    """Temporada ativa + top-2 das encerradas (com apelido quando disponível)."""
    seasons = (await db.execute(
        select(Season).order_by(Season.id.desc())
    )).scalars().all()

    # Mapeia player_id → apelido para enriquecer ranking_final
    players_map: dict[int, str | None] = {}
    player_ids = {
        entry["player_id"]
        for s in seasons if s.ranking_final
        for entry in (s.ranking_final[:2] if s.ranking_final else [])
    }
    if player_ids:
        rows = (await db.execute(
            select(Player.id, Player.apelido).where(Player.id.in_(player_ids))
        )).all()
        players_map = {r.id: r.apelido for r in rows}

    ativa = next((s for s in seasons if s.status == StatusTemporada.ATIVA), None)
    encerradas = [s for s in seasons if s.status == StatusTemporada.ENCERRADA]

    def top2(season: Season) -> list:
        if not season.ranking_final:
            return []
        top = season.ranking_final[:2]
        result = []
        for entry in top:
            pid = entry.get("player_id")
            apelido = players_map.get(pid) if pid else None
            nome = entry.get("nome", "")
            partes = nome.strip().split()
            nome_exib = apelido or (
                f"{partes[0]} {partes[-1]}" if len(partes) > 1 else nome
            )
            result.append({
                "posicao": entry.get("posicao"),
                "nome": nome_exib,
                "pontos": entry.get("pontos"),
            })
        return result

    return {
        "ativa": {
            "id": ativa.id,
            "data_inicio": ativa.data_inicio.isoformat(),
            "data_fim": ativa.data_fim.isoformat(),
        } if ativa else None,
        "encerradas": [
            {
                "id": s.id,
                "data_inicio": s.data_inicio.isoformat(),
                "data_fim": s.data_fim.isoformat(),
                "top2": top2(s),
            }
            for s in encerradas
        ],
    }


@router.get("/horarios-semana")
async def horarios_semana(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(HorarioDiaSemana).order_by(HorarioDiaSemana.dia_semana)
    )).scalars().all()
    return [
        {
            "dia_semana": r.dia_semana,
            "aberto": r.aberto,
            "hora_abertura": r.hora_abertura,
            "hora_fechamento": r.hora_fechamento,
        }
        for r in rows
    ]
