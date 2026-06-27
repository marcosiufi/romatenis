from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.auth import get_current_admin, get_current_player
from app.core.config import settings
from app.core.database import get_db
from app.models.configuracao import Configuracao
from app.models.player import Player
from app.services.subscription_service import PLANO_MESES, PLANO_PARCELAS
from app.schemas.subscription import (
    PausaRequest,
    SubscriptionAdminOut,
    SubscriptionAdminUpdate,
    SubscriptionCreate,
    SubscriptionCreateOut,
    SubscriptionOut,
    SubscriptionRenovar,
)
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


@router.get("", response_model=list[SubscriptionAdminOut])
async def listar_todas(
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    subs = await svc.listar_todas()
    result = []
    for s in subs:
        out = SubscriptionAdminOut.model_validate(s)
        if s.player:
            out.player_nome = s.player.nome
            out.player_email = s.player.email
        result.append(out)
    return result


@router.patch("/{sub_id}/status", response_model=SubscriptionOut)
async def admin_atualizar_status(
    sub_id: int,
    body: SubscriptionAdminUpdate,
    _admin: Player = Depends(get_current_admin),
    svc: SubscriptionService = Depends(_svc),
):
    try:
        return await svc.admin_atualizar_status(
            sub_id, body.status, body.data_pausa, body.data_retorno_prevista, body.notas
        )
    except SubscriptionError as e:
        raise HTTPException(422, str(e))


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


# ── Preços padrão (público, usado pelo frontend) ───────────────────────────────

@router.get("/precos")
async def precos(db=Depends(get_db)):
    """Retorna preços e parcelas de cada plano lidos do banco."""
    from app.models.subscription import PlanoAssinatura
    cfg = await Configuracao.get(db)
    totais = {
        "mensal":      float(cfg.preco_mensal),
        "trimestral":  float(cfg.preco_trimestral),
        "semestral":   float(cfg.preco_semestral),
        "anual":       float(cfg.preco_anual),
        "locacao_hora": float(cfg.preco_locacao_hora),
    }
    result = {}
    for plano in PlanoAssinatura:
        total = totais[plano.value]
        meses = PLANO_MESES[plano]
        result[plano.value] = {
            "valor_total":  total,
            "valor_mensal": round(total / meses, 2),
            "parcelas":     PLANO_PARCELAS[plano],
        }
    result["locacao_hora"] = totais["locacao_hora"]
    return result


# ── Player ────────────────────────────────────────────────────────────────────

@router.post("/contratar", response_model=SubscriptionCreateOut)
async def contratar_plano(
    body: SubscriptionRenovar,
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    """Contratação de novo plano pelo próprio jogador (landing page)."""
    try:
        res = await svc.contratar(player, body.plano, body.forma_pagamento)
    except SubscriptionError as e:
        raise HTTPException(422, str(e))
    out = SubscriptionCreateOut.model_validate(res.subscription)
    out.payment_link = res.payment_link
    out.pix_qrcode_base64 = res.pix_qrcode_base64
    out.pix_copia_e_cola = res.pix_copia_e_cola
    out.contrato_link = res.contrato_link
    return out


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


@router.post("/renovar", response_model=SubscriptionCreateOut)
async def renovar(
    body: SubscriptionRenovar,
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    try:
        res = await svc.renovar(player, body.plano, body.forma_pagamento)
    except SubscriptionError as e:
        raise HTTPException(422, str(e))

    out = SubscriptionCreateOut.model_validate(res.subscription)
    out.payment_link = res.payment_link
    out.pix_qrcode_base64 = res.pix_qrcode_base64
    out.pix_copia_e_cola = res.pix_copia_e_cola
    return out


@router.post("/solicitar-pausa")
async def solicitar_pausa(
    body: PausaRequest,
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    try:
        await svc.solicitar_pausa(player, body.motivo, body.data_inicio, body.dias_pausa)
    except SubscriptionError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "msg": "Solicitação enviada. O admin entrará em contato."}


@router.get("/pix-pendente", response_model=SubscriptionCreateOut | None)
async def pix_pendente(
    player: Player = Depends(get_current_player),
    svc: SubscriptionService = Depends(_svc),
):
    res = await svc.get_pix_pendente(player)
    if not res:
        return None
    out = SubscriptionCreateOut.model_validate(res.subscription)
    out.payment_link = res.payment_link
    out.pix_qrcode_base64 = res.pix_qrcode_base64
    out.pix_copia_e_cola = res.pix_copia_e_cola
    return out


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
