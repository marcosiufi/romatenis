"""
Endpoints de webhook — chamados pelo N8N, não pelo browser.

POST /webhooks/n8n/reply      — resposta de jogador a convite de matchmaking
POST /webhooks/n8n/status     — atualização de status de entrega WhatsApp (opcional)
POST /matchmaking/executar    — dispara matchmaking para uma data (admin)
GET  /matchmaking/convites    — lista convites ativos (admin)
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.auth import get_current_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.match import TipoPartida
from app.models.match_invitation import MatchInvitation, StatusRodadaMatchmaking
from app.models.player import Player
from app.services.matchmaking_service import MatchmakingService
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = APIRouter(tags=["webhooks"])

def _mm_svc(db=Depends(get_db)) -> MatchmakingService:
    return MatchmakingService(db)


def _validar_n8n(x_n8n_secret: str | None = Header(default=None, alias="X-N8N-Secret")) -> None:
    if settings.N8N_SECRET and x_n8n_secret != settings.N8N_SECRET:
        raise HTTPException(401, "Token N8N inválido")


# ── Webhook N8N ───────────────────────────────────────────────────────────────

class ReplyPayload(BaseModel):
    wamid_convite: str
    aceita: bool


@router.post("/webhooks/n8n/reply")
async def n8n_reply(
    body: ReplyPayload,
    _: None = Depends(_validar_n8n),
    svc: MatchmakingService = Depends(_mm_svc),
):
    return await svc.processar_resposta(body.wamid_convite, body.aceita)


@router.post("/webhooks/n8n/status")
async def n8n_status(
    body: dict,
    _: None = Depends(_validar_n8n),
):
    """Recebe updates de entrega/leitura do N8N — apenas loga por enquanto."""
    return {"recebido": True, "event": body.get("event")}


# ── Matchmaking (admin) ───────────────────────────────────────────────────────

@router.post("/matchmaking/executar")
async def executar_matchmaking(
    data: str,
    tipo: TipoPartida = TipoPartida.SIMPLES,
    _admin: Player = Depends(get_current_admin),
    svc: MatchmakingService = Depends(_mm_svc),
):
    """
    Dispara o algoritmo de matchmaking para uma data.
    Parâmetros: ?data=2026-06-22&tipo=simples|duplas
    """
    try:
        return await svc.executar(data, tipo)
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/matchmaking/convites")
async def listar_convites(
    _admin: Player = Depends(get_current_admin),
    db=Depends(get_db),
):
    result = await db.execute(
        select(MatchInvitation)
        .options(selectinload(MatchInvitation.jogadores))
        .order_by(MatchInvitation.criado_em.desc())
        .limit(50)
    )
    convites = result.scalars().all()
    return [
        {
            "id": c.id,
            "tipo": c.tipo.value,
            "slot_data_hora": c.slot_data_hora.isoformat(),
            "status": c.status.value,
            "expira_em": c.expira_em.isoformat(),
            "booking_id": c.booking_id,
            "jogadores": [
                {
                    "player_id": jp.player_id,
                    "lado": jp.lado_proposto,
                    "status": jp.status.value,
                }
                for jp in c.jogadores
            ],
        }
        for c in convites
    ]
