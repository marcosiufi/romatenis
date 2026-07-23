from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, select

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.lista_espera import ListaEspera, StatusListaEspera
from app.models.contrato import ContratoClausula
from app.models.horario_dia_semana import HorarioDiaSemana
from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.payment import Payment
from app.models.configuracao import Configuracao
from app.models.horario_especial import HorarioEspecial
from app.models.slot_ranking import SlotRanking
from app.models.match import Match, StatusPartida
from app.models.player import NivelJogador, Player, StatusJogador
from app.models.season import Season, StatusTemporada
from app.models.subscription import StatusAssinatura, Subscription
from app.models.cupom import Cupom
from app.schemas.cupom import CupomCreate, CupomOut, CupomUpdate
from app.schemas.player import PlayerOut

router = APIRouter(prefix="/admin", tags=["admin"])
FUSO_BR = ZoneInfo("America/Sao_Paulo")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    agora = datetime.now(timezone.utc)
    hoje_br = datetime.now(FUSO_BR).date()
    hoje_ini = datetime.combine(hoje_br, time.min, tzinfo=FUSO_BR)
    hoje_fim = hoje_ini + timedelta(days=1)

    total_jogadores = await db.scalar(select(func.count(Player.id))) or 0
    assinaturas_ativas = (
        await db.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.status == StatusAssinatura.ATIVA,
                Subscription.data_expiracao > agora,
            )
        )
    ) or 0

    season_row = (
        await db.execute(
            select(Season).where(Season.status == StatusTemporada.ATIVA).limit(1)
        )
    ).scalar_one_or_none()

    lider_row = (
        await db.execute(
            select(Player)
            .order_by(Player.pontos_ranking_temporada_atual.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    partidas_sem_placar = (
        await db.scalar(
            select(func.count(Match.id)).where(
                Match.status == StatusPartida.AGENDADO,
                Match.data_hora < agora,
            )
        )
    ) or 0

    reservas_hoje = (
        await db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio >= hoje_ini,
                Booking.data_hora_inicio < hoje_fim,
            )
        )
    ) or 0

    pausas_pendentes = (
        await db.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.pausa_solicitada == True,  # noqa: E712
            )
        )
    ) or 0

    # Assinou e pagou, mas a Autentique nunca chegou a enviar o contrato:
    # o jogador fica bloqueado sem que nada apareça no painel.
    contratos_nao_enviados = (
        await db.scalar(
            select(func.count(func.distinct(Player.id)))
            .select_from(Player)
            .join(Subscription, Subscription.player_id == Player.id)
            .where(
                Player.contrato_enviado_em.is_(None),
                Player.contrato_assinado.is_(False),
                Subscription.status != StatusAssinatura.CANCELADA,
            )
        )
    ) or 0

    return {
        "total_jogadores": total_jogadores,
        "assinaturas_ativas": assinaturas_ativas,
        "partidas_sem_placar": partidas_sem_placar,
        "reservas_hoje": reservas_hoje,
        "temporada_ativa": (
            {
                "id": season_row.id,
                "data_inicio": season_row.data_inicio.isoformat(),
                "data_fim": season_row.data_fim.isoformat(),
            }
            if season_row
            else None
        ),
        "lider_ranking": (
            {
                "id": lider_row.id,
                "nome": lider_row.nome,
                "pontos": lider_row.pontos_ranking_temporada_atual,
                "nivel": lider_row.nivel.value,
            }
            if lider_row and lider_row.pontos_ranking_temporada_atual > 0
            else None
        ),
        "pausas_pendentes": pausas_pendentes,
        "contratos_nao_enviados": contratos_nao_enviados,
    }


# ── Players (admin-only fields) ───────────────────────────────────────────────

@router.get("/players", response_model=list[PlayerOut])
async def list_all_players(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Admin — lista todos os jogadores independente de status."""
    result = await db.execute(
        select(Player).order_by(Player.nome)
    )
    return result.scalars().all()


class AdminPlayerPatch(BaseModel):
    nome: str | None = None
    telefone: str | None = None
    email: EmailStr | None = None
    aceita_convites_sistema: bool | None = None
    nivel: NivelJogador | None = None
    is_admin: bool | None = None
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
    status: StatusJogador | None = None


@router.patch("/players/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: int,
    body: AdminPlayerPatch,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Atualiza campos de um jogador incluindo nivel e is_admin."""
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(404, "Jogador não encontrado")
    data = body.model_dump(exclude_none=True)
    if "status" in data:
        novo_status = data["status"]
        if novo_status == StatusJogador.INATIVO and player.status != StatusJogador.INATIVO.value:
            data["data_inativacao"] = datetime.now(timezone.utc)
        elif novo_status == StatusJogador.ATIVO:
            data["data_inativacao"] = None
        data["status"] = novo_status.value
    for field, value in data.items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player


# ── Configurações (preços) ────────────────────────────────────────────────────

class ConfiguracaoIn(BaseModel):
    preco_mensal: float
    preco_trimestral: float
    preco_semestral: float
    preco_anual: float
    preco_locacao_hora: float
    preco_jogo_avulso: float
    # Disponibilidade comercial
    contratacao_planos_ativa: bool
    reservas_ativas: bool
    msg_planos_desabilitado: str
    msg_reservas_desabilitado: str
    # Antecedências (horas)
    ranking_antecedencia_minima_horas: int = Field(ge=0, le=168)
    ranking_ultima_hora_horas: int = Field(ge=0, le=168)
    jogo_avulso_ultima_hora_horas: int = Field(ge=0, le=168)
    locacao_libera_slot_ranking_horas: int = Field(ge=0, le=168)

    @model_validator(mode="after")
    def validar_janelas(self) -> "ConfiguracaoIn":
        # Última hora ≥ mínima anularia a reserva antecipada do ranking:
        # todo slot cairia na janela de última hora.
        if self.ranking_ultima_hora_horas >= self.ranking_antecedencia_minima_horas:
            raise ValueError(
                "A janela de última hora do ranking deve ser menor que a "
                "antecedência mínima."
            )
        for campo, rotulo in (
            ("msg_planos_desabilitado", "planos"),
            ("msg_reservas_desabilitado", "reservas"),
        ):
            if not getattr(self, campo).strip():
                raise ValueError(f"A mensagem de {rotulo} desabilitado não pode ficar vazia.")
        return self


@router.get("/configuracoes")
async def get_configuracoes(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    cfg = await Configuracao.get(db)
    return {
        "preco_mensal":       float(cfg.preco_mensal),
        "preco_trimestral":   float(cfg.preco_trimestral),
        "preco_semestral":    float(cfg.preco_semestral),
        "preco_anual":        float(cfg.preco_anual),
        "preco_locacao_hora": float(cfg.preco_locacao_hora),
        "preco_jogo_avulso":  float(cfg.preco_jogo_avulso),
        "contratacao_planos_ativa":  cfg.contratacao_planos_ativa,
        "reservas_ativas":           cfg.reservas_ativas,
        "msg_planos_desabilitado":   cfg.msg_planos_desabilitado,
        "msg_reservas_desabilitado": cfg.msg_reservas_desabilitado,
        "ranking_antecedencia_minima_horas": cfg.ranking_antecedencia_minima_horas,
        "ranking_ultima_hora_horas":         cfg.ranking_ultima_hora_horas,
        "jogo_avulso_ultima_hora_horas":     cfg.jogo_avulso_ultima_hora_horas,
        "locacao_libera_slot_ranking_horas": cfg.locacao_libera_slot_ranking_horas,
    }


@router.put("/configuracoes")
async def put_configuracoes(
    body: ConfiguracaoIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    cfg = await Configuracao.get(db)
    # Só a transição desligado → ligado avisa a lista de espera; salvar a tela
    # de novo com o toggle já ligado não reenvia nada.
    abriu_contratacao = body.contratacao_planos_ativa and not cfg.contratacao_planos_ativa

    cfg.preco_mensal       = body.preco_mensal
    cfg.preco_trimestral   = body.preco_trimestral
    cfg.preco_semestral    = body.preco_semestral
    cfg.preco_anual        = body.preco_anual
    cfg.preco_locacao_hora = body.preco_locacao_hora
    cfg.preco_jogo_avulso  = body.preco_jogo_avulso

    cfg.contratacao_planos_ativa  = body.contratacao_planos_ativa
    cfg.reservas_ativas           = body.reservas_ativas
    cfg.msg_planos_desabilitado   = body.msg_planos_desabilitado.strip()
    cfg.msg_reservas_desabilitado = body.msg_reservas_desabilitado.strip()

    cfg.ranking_antecedencia_minima_horas = body.ranking_antecedencia_minima_horas
    cfg.ranking_ultima_hora_horas         = body.ranking_ultima_hora_horas
    cfg.jogo_avulso_ultima_hora_horas     = body.jogo_avulso_ultima_hora_horas
    cfg.locacao_libera_slot_ranking_horas = body.locacao_libera_slot_ranking_horas

    await db.commit()

    avisados = 0
    if abriu_contratacao:
        from app.services.subscription_service import SubscriptionService
        avisados = await SubscriptionService(db).avisar_lista_espera_abertura()

    return {"ok": True, "lista_espera_avisada": avisados}


# ── Diagnóstico de e-mail ─────────────────────────────────────────────────────

@router.get("/email/status")
async def email_status(_admin: Player = Depends(get_current_admin)):
    """Mostra como o SMTP está configurado, sem expor a senha."""
    from app.core.config import settings
    from app.services import email_service

    return {
        "configurado": bool(settings.SMTP_HOST and settings.SMTP_USER),
        "host": settings.SMTP_HOST or None,
        "porta": settings.SMTP_PORT,
        "usuario": settings.SMTP_USER or None,
        "senha_definida": bool(settings.SMTP_PASS),
        "remetente": email_service.remetente() or None,
        "remetente_nome": settings.SMTP_FROM_NAME,
        # Alias exige autorização no provedor; sinaliza para conferência
        "usa_alias": bool(settings.SMTP_FROM.strip())
        and settings.SMTP_FROM.strip() != settings.SMTP_USER,
    }


class TesteEmailIn(BaseModel):
    destinatario: EmailStr


@router.post("/email/testar")
async def testar_email(
    body: TesteEmailIn,
    admin: Player = Depends(get_current_admin),
):
    """Envia um e-mail de teste e devolve o erro real do servidor SMTP."""
    from app.services import email_service

    corpo = (
        '<p style="color:#333">Se você está lendo isto, o envio de e-mails do '
        "Roma Tênis está funcionando. ✅</p>"
        '<p style="color:#888;font-size:.85rem">Disparado pelo painel administrativo.</p>'
    )
    try:
        await email_service.send_email_estrito(
            body.destinatario,
            "✅ Teste de envio — Roma Tênis",
            email_service._html_base("Teste de configuração", corpo),
        )
    except email_service.EmailNaoConfigurado as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, email_service.explicar_erro_smtp(e))

    return {"ok": True, "enviado_para": body.destinatario,
            "remetente": email_service.remetente()}


# ── Cupons de desconto ────────────────────────────────────────────────────────

@router.get("/cupons", response_model=list[CupomOut])
async def listar_cupons(_admin: Player = Depends(get_current_admin), db=Depends(get_db)):
    rows = (await db.execute(select(Cupom).order_by(Cupom.criado_em.desc()))).scalars().all()
    return list(rows)


@router.post("/cupons", response_model=CupomOut, status_code=201)
async def criar_cupom(body: CupomCreate, _admin: Player = Depends(get_current_admin), db=Depends(get_db)):
    existe = (await db.execute(
        select(Cupom).where(func.upper(Cupom.codigo) == body.codigo)
    )).scalar_one_or_none()
    if existe:
        raise HTTPException(409, "Já existe um cupom com esse código.")
    if body.validade_inicio and body.validade_fim and body.validade_fim <= body.validade_inicio:
        raise HTTPException(422, "A data final deve ser posterior à inicial.")

    cupom = Cupom(
        codigo=body.codigo,
        percentual=body.percentual,
        descricao=body.descricao,
        validade_inicio=body.validade_inicio,
        validade_fim=body.validade_fim,
        max_usos=body.max_usos,
        ativo=body.ativo,
    )
    db.add(cupom)
    await db.commit()
    await db.refresh(cupom)
    return cupom


@router.patch("/cupons/{cupom_id}", response_model=CupomOut)
async def atualizar_cupom(
    cupom_id: int, body: CupomUpdate,
    _admin: Player = Depends(get_current_admin), db=Depends(get_db),
):
    cupom = await db.get(Cupom, cupom_id)
    if not cupom:
        raise HTTPException(404, "Cupom não encontrado.")
    dados = body.model_dump(exclude_unset=True)
    for campo, valor in dados.items():
        setattr(cupom, campo, valor)
    ini = cupom.validade_inicio
    fim = cupom.validade_fim
    if ini and fim and fim <= ini:
        raise HTTPException(422, "A data final deve ser posterior à inicial.")
    await db.commit()
    await db.refresh(cupom)
    return cupom


@router.delete("/cupons/{cupom_id}", status_code=204)
async def excluir_cupom(cupom_id: int, _admin: Player = Depends(get_current_admin), db=Depends(get_db)):
    cupom = await db.get(Cupom, cupom_id)
    if not cupom:
        raise HTTPException(404, "Cupom não encontrado.")
    await db.delete(cupom)
    await db.commit()


# ── Contratos (Autentique) ────────────────────────────────────────────────────

@router.post("/players/{player_id}/enviar-contrato", response_model=PlayerOut)
async def enviar_contrato(
    player_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Gera e envia o Termo de Adesão via Autentique para o jogador (WhatsApp)."""
    from app.services.autentique_client import AutentiqueClient, AutentiqueError

    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(404, "Jogador não encontrado")

    client = AutentiqueClient()
    try:
        doc_id, link = await client.enviar_contrato(
            nome=player.nome,
            email=player.email,
            cpf=player.cpf,
            telefone=player.telefone,
        )
    except AutentiqueError as exc:
        raise HTTPException(502, f"Erro Autentique: {exc}")

    player.contrato_autentique_id = doc_id
    player.contrato_link_assinatura = link
    player.contrato_enviado_em = datetime.now(timezone.utc)
    player.contrato_assinado = False
    player.contrato_assinado_em = None
    await db.commit()
    await db.refresh(player)

    return player


@router.post("/players/{player_id}/marcar-contrato-assinado", response_model=PlayerOut)
async def marcar_contrato_assinado(
    player_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Admin confirma manualmente que o contrato foi assinado (fallback)."""
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(404, "Jogador não encontrado")
    player.contrato_assinado = True
    player.contrato_assinado_em = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(player)
    return player


# ── Slots de Ranking ──────────────────────────────────────────────────────────

class SlotRankingIn(BaseModel):
    dia_semana: int   # 0=segunda … 6=domingo
    hora_inicio: time
    hora_fim: time
    ativo: bool = True


class SlotRankingOut(BaseModel):
    id: int
    dia_semana: int
    hora_inicio: time
    hora_fim: time
    ativo: bool

    model_config = {"from_attributes": True}


DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


@router.get("/slots-ranking", response_model=list[SlotRankingOut])
async def listar_slots_ranking(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    result = await db.execute(
        select(SlotRanking).order_by(SlotRanking.dia_semana, SlotRanking.hora_inicio)
    )
    return result.scalars().all()


@router.post("/slots-ranking", response_model=SlotRankingOut, status_code=201)
async def criar_slot_ranking(
    body: SlotRankingIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    if not (0 <= body.dia_semana <= 6):
        raise HTTPException(422, "Dia da semana inválido (0=segunda, 6=domingo).")
    if body.hora_inicio >= body.hora_fim:
        raise HTTPException(422, "Hora de início deve ser anterior à hora de fim.")

    slot = SlotRanking(
        dia_semana=body.dia_semana,
        hora_inicio=body.hora_inicio,
        hora_fim=body.hora_fim,
        ativo=body.ativo,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return slot


@router.put("/slots-ranking/{slot_id}", response_model=SlotRankingOut)
async def atualizar_slot_ranking(
    slot_id: int,
    body: SlotRankingIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    if not (0 <= body.dia_semana <= 6):
        raise HTTPException(422, "Dia da semana inválido (0=segunda, 6=domingo).")
    if body.hora_inicio >= body.hora_fim:
        raise HTTPException(422, "Hora de início deve ser anterior à hora de fim.")
    slot = await db.get(SlotRanking, slot_id)
    if not slot:
        raise HTTPException(404, "Slot não encontrado.")
    slot.dia_semana = body.dia_semana
    slot.hora_inicio = body.hora_inicio
    slot.hora_fim = body.hora_fim
    slot.ativo = body.ativo
    await db.commit()
    await db.refresh(slot)
    return slot


@router.patch("/slots-ranking/{slot_id}/toggle", response_model=SlotRankingOut)
async def toggle_slot_ranking(
    slot_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    slot = await db.get(SlotRanking, slot_id)
    if not slot:
        raise HTTPException(404, "Slot não encontrado.")
    slot.ativo = not slot.ativo
    await db.commit()
    await db.refresh(slot)
    return slot


@router.delete("/slots-ranking/{slot_id}", status_code=204)
async def deletar_slot_ranking(
    slot_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    slot = await db.get(SlotRanking, slot_id)
    if not slot:
        raise HTTPException(404, "Slot não encontrado.")
    await db.delete(slot)
    await db.commit()


# ── Locações de Quadra ────────────────────────────────────────────────────────

class LocacaoOut(BaseModel):
    id: int
    data_hora_inicio: datetime
    data_hora_fim: datetime
    status: str
    valor: float
    jogador_nome: str | None = None
    jogador_email: str | None = None
    pagamento_status: str | None = None
    pagamento_metodo: str | None = None


@router.get("/locacoes", response_model=list[LocacaoOut])
async def listar_locacoes(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    rows = (await db.execute(
        select(Booking, Player, Payment)
        .outerjoin(Player, Booking.jogador_responsavel_id == Player.id)
        .outerjoin(Payment, Payment.booking_id == Booking.id)
        .where(Booking.tipo == TipoReserva.LOCACAO_AVULSA)
        .order_by(Booking.data_hora_inicio.desc())
        .limit(200)
    )).all()
    return [
        LocacaoOut(
            id=b.id,
            data_hora_inicio=b.data_hora_inicio,
            data_hora_fim=b.data_hora_fim,
            status=b.status.value,
            valor=float(b.valor or 0),
            jogador_nome=p.nome if p else b.cliente_locacao_nome,
            jogador_email=p.email if p else None,
            pagamento_status=pay.status.value if pay else None,
            pagamento_metodo=pay.metodo.value if pay else None,
        )
        for b, p, pay in rows
    ]


@router.patch("/locacoes/{booking_id}/cancelar")
async def cancelar_locacao(
    booking_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    booking = await db.get(Booking, booking_id)
    if not booking or booking.tipo != TipoReserva.LOCACAO_AVULSA:
        raise HTTPException(404, "Locação não encontrada.")
    if booking.status == StatusReserva.CANCELADA:
        raise HTTPException(400, "Locação já está cancelada.")
    booking.status = StatusReserva.CANCELADA
    await db.commit()
    return {"ok": True}


# ── Feriados e Horários Especiais ─────────────────────────────────────────────

class HorarioEspecialIn(BaseModel):
    data: date
    descricao: str
    fechado: bool = False
    hora_abertura: int | None = None
    hora_fechamento: int | None = None


class HorarioEspecialOut(BaseModel):
    id: int
    data: date
    descricao: str
    fechado: bool
    hora_abertura: int | None = None
    hora_fechamento: int | None = None

    model_config = {"from_attributes": True}


@router.get("/horarios-especiais", response_model=list[HorarioEspecialOut])
async def listar_horarios_especiais(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    return (await db.execute(
        select(HorarioEspecial).order_by(HorarioEspecial.data)
    )).scalars().all()


@router.post("/horarios-especiais", response_model=HorarioEspecialOut, status_code=201)
async def criar_horario_especial(
    body: HorarioEspecialIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    if await db.scalar(select(HorarioEspecial).where(HorarioEspecial.data == body.data)):
        raise HTTPException(409, "Já existe um horário especial para esta data.")
    he = HorarioEspecial(**body.model_dump())
    db.add(he)
    await db.commit()
    await db.refresh(he)
    return he


@router.put("/horarios-especiais/{he_id}", response_model=HorarioEspecialOut)
async def atualizar_horario_especial(
    he_id: int,
    body: HorarioEspecialIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    he = await db.get(HorarioEspecial, he_id)
    if not he:
        raise HTTPException(404, "Não encontrado.")
    conflito = await db.scalar(
        select(HorarioEspecial).where(HorarioEspecial.data == body.data, HorarioEspecial.id != he_id)
    )
    if conflito:
        raise HTTPException(409, "Já existe um horário especial para esta data.")
    for k, v in body.model_dump().items():
        setattr(he, k, v)
    await db.commit()
    await db.refresh(he)
    return he


@router.delete("/horarios-especiais/{he_id}", status_code=204)
async def deletar_horario_especial(
    he_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    he = await db.get(HorarioEspecial, he_id)
    if not he:
        raise HTTPException(404, "Não encontrado.")
    await db.delete(he)
    await db.commit()


# ── Lista de Espera ───────────────────────────────────────────────────────────

@router.get("/lista-espera")
async def admin_lista_espera(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    from app.services.subscription_service import SubscriptionService
    svc = SubscriptionService(db)
    fila = await svc.listar_fila_espera()
    vagas = await svc.vagas_ranking()
    return {"fila": fila, "vagas": vagas}


@router.delete("/lista-espera/{entrada_id}", status_code=204)
async def admin_remover_lista_espera(
    entrada_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    from app.services.subscription_service import SubscriptionError, SubscriptionService
    svc = SubscriptionService(db)
    try:
        await svc.admin_remover_da_fila(entrada_id)
    except SubscriptionError as e:
        raise HTTPException(404, str(e))


@router.post("/lista-espera/{entrada_id}/convocar")
async def admin_convocar_lista_espera(
    entrada_id: int,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    from app.services.subscription_service import SubscriptionError, SubscriptionService
    svc = SubscriptionService(db)
    try:
        await svc.admin_convocar_da_fila(entrada_id)
    except SubscriptionError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.post("/verificar-convocacoes-expiradas")
async def verificar_convocacoes_expiradas(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    from app.services.subscription_service import SubscriptionService
    svc = SubscriptionService(db)
    n = await svc.verificar_convocacoes_expiradas()
    return {"expiradas": n}


# ── Dados da empresa ──────────────────────────────────────────────────────────

class EmpresaIn(BaseModel):
    razao_social: str
    nome_fantasia: str
    cnpj: str
    cpf_responsavel: str
    end_logradouro: str
    end_numero: str
    end_complemento: str = ""
    end_bairro: str
    end_cidade: str
    end_estado: str
    end_pais: str
    end_cep: str
    whatsapp: str
    instagram: str
    email_contato: str


@router.get("/empresa")
async def get_empresa(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    cfg = await Configuracao.get(db)
    return {
        "razao_social":    cfg.razao_social,
        "nome_fantasia":   cfg.nome_fantasia,
        "cnpj":            cfg.cnpj,
        "cpf_responsavel": cfg.cpf_responsavel,
        "end_logradouro":  cfg.end_logradouro,
        "end_numero":      cfg.end_numero,
        "end_complemento": cfg.end_complemento,
        "end_bairro":      cfg.end_bairro,
        "end_cidade":      cfg.end_cidade,
        "end_estado":      cfg.end_estado,
        "end_pais":        cfg.end_pais,
        "end_cep":         cfg.end_cep,
        "whatsapp":        cfg.whatsapp,
        "instagram":       cfg.instagram,
        "email_contato":   cfg.email_contato,
    }


@router.put("/empresa")
async def put_empresa(
    body: EmpresaIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    cfg = await Configuracao.get(db)
    cfg.razao_social    = body.razao_social.strip()
    cfg.nome_fantasia   = body.nome_fantasia.strip()
    cfg.cnpj            = body.cnpj.strip()
    cfg.cpf_responsavel = body.cpf_responsavel.strip()
    cfg.end_logradouro  = body.end_logradouro.strip()
    cfg.end_numero      = body.end_numero.strip()
    cfg.end_complemento = body.end_complemento.strip()
    cfg.end_bairro      = body.end_bairro.strip()
    cfg.end_cidade      = body.end_cidade.strip()
    cfg.end_estado      = body.end_estado.strip().upper()[:2]
    cfg.end_pais        = body.end_pais.strip()
    cfg.end_cep         = body.end_cep.strip()
    cfg.whatsapp        = "".join(c for c in body.whatsapp if c.isdigit())
    cfg.instagram       = body.instagram.strip().lstrip("@")
    cfg.email_contato   = body.email_contato.strip()
    await db.commit()
    return {"ok": True}


# ── Contrato ─────────────────────────────────────────────────────────────────

class ClausulaIn(BaseModel):
    titulo: str
    texto: str
    ativo: bool = True


@router.get("/contrato/clausulas")
async def listar_clausulas(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    rows = (await db.execute(
        select(ContratoClausula).order_by(ContratoClausula.ordem)
    )).scalars().all()
    return [
        {"id": r.id, "ordem": r.ordem, "titulo": r.titulo, "texto": r.texto, "ativo": r.ativo}
        for r in rows
    ]


@router.put("/contrato/clausulas")
async def salvar_clausulas(
    clausulas: list[ClausulaIn],
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Substitui todas as cláusulas pela lista recebida (mantém a ordem da lista)."""
    # Remove todas existentes
    existing = (await db.execute(select(ContratoClausula))).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    # Insere as novas na ordem recebida
    for i, c in enumerate(clausulas, start=1):
        db.add(ContratoClausula(
            ordem=i,
            titulo=c.titulo.strip(),
            texto=c.texto.strip(),
            ativo=c.ativo,
        ))

    await db.commit()
    return {"ok": True, "total": len(clausulas)}


# ── Horários por dia da semana ────────────────────────────────────────────────

class HorarioDiaIn(BaseModel):
    dia_semana: int
    aberto: bool
    hora_abertura: int
    hora_fechamento: int


@router.get("/horarios-semana")
async def get_horarios_semana(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
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


@router.put("/horarios-semana")
async def put_horarios_semana(
    horarios: list[HorarioDiaIn],
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    for h in horarios:
        row = await db.get(HorarioDiaSemana, h.dia_semana)
        if row:
            row.aberto = h.aberto
            row.hora_abertura = h.hora_abertura
            row.hora_fechamento = h.hora_fechamento
        else:
            db.add(HorarioDiaSemana(
                dia_semana=h.dia_semana,
                aberto=h.aberto,
                hora_abertura=h.hora_abertura,
                hora_fechamento=h.hora_fechamento,
            ))
    await db.commit()
    return {"ok": True}

