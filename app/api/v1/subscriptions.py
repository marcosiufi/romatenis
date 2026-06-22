from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.auth import get_current_admin, get_current_player
from app.core.config import settings
from app.core.database import get_db
from app.models.player import Player
from app.schemas.subscription import SubscriptionCreate, SubscriptionCreateOut, SubscriptionOut
from app.services.subscription_service import SubscriptionError, SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _svc(db=Depends(get_db)) -> SubscriptionService:
    return SubscriptionService(db)


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=SubscriptionCreateOut)
async def criar(
    body: SubscriptionCreate,
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    try:
        res = await svc.criar_assinatura(
            body.player_id, body.plano, body.forma_pagamento, body.valor_mensal, body.parcelas
        )
    except SubscriptionError as e:
        raise HTTPException(422, str(e))

    out = SubscriptionCreateOut.model_validate(res.subscription)
    out.payment_link = res.payment_link
    out.pix_qrcode_base64 = res.pix_qrcode_base64
    out.pix_copia_e_cola = res.pix_copia_e_cola
    return out


@router.get("", response_model=list[SubscriptionOut])
async def listar_todas(
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    return await svc.listar_todas()


@router.post("/{sub_id}/antecipar", response_model=SubscriptionOut)
async def antecipar(
    sub_id: int,
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    try:
        return await svc.solicitar_antecipacao(sub_id)
    except SubscriptionError as e:
        raise HTTPException(422, str(e))


@router.post("/verificar-expiracoes")
async def verificar_expiracoes(
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    n = await svc.verificar_expiracoes()
    return {"expiradas": n}


# ── Player ────────────────────────────────────────────────────────────────────

@router.get("/minhas", response_model=list[SubscriptionOut])
async def listar_minhas(
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    return await svc.listar_minhas(player)


@router.get("/minha-ativa", response_model=SubscriptionOut | None)
async def minha_ativa(
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    return await svc.minha_ativa(player)


# ── Webhook Asaas (público, validado por token) ───────────────────────────────

@router.post("/webhook")
async def webhook(
    request: Request,
    svc: SubscriptionService = Depends(_svc),
    asaas_access_token: str | None = Header(default=None, alias="asaas-access-token"),
):
    if settings.ASAAS_WEBHOOK_TOKEN and asaas_access_token != settings.ASAAS_WEBHOOK_TOKEN:
        raise HTTPException(401, "Token de webhook inválido")

    body = await request.json()
    event: str = body.get("event", "")
    payment_data: dict = body.get("payment", {})

    await svc.processar_webhook(event, payment_data)
    return {"received": True}
