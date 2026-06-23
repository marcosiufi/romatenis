from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.booking import Booking, StatusReserva
from app.models.match import Match, StatusPartida
from app.models.player import NivelJogador, Player
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
    }


# ── Players (admin-only fields) ───────────────────────────────────────────────

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
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player
