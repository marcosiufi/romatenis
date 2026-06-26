from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.booking import Booking, StatusReserva
from app.models.configuracao import Configuracao
from app.models.slot_ranking import SlotRanking
from app.models.match import Match, StatusPartida
from app.models.player import NivelJogador, Player, StatusJogador
from app.models.season import Season, StatusTemporada
from app.models.subscription import StatusAssinatura, Subscription
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
    }


@router.put("/configuracoes")
async def put_configuracoes(
    body: ConfiguracaoIn,
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    cfg = await Configuracao.get(db)
    cfg.preco_mensal       = body.preco_mensal
    cfg.preco_trimestral   = body.preco_trimestral
    cfg.preco_semestral    = body.preco_semestral
    cfg.preco_anual        = body.preco_anual
    cfg.preco_locacao_hora = body.preco_locacao_hora
    await db.commit()
    return {"ok": True}


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
