"""
Webhook do Autentique — recebe eventos de assinatura de contratos.

Autentique envia POST com JSON quando um documento é assinado/finalizado.
Payload esperado:
  { "event": "document.finished", "data": { "id": "<document_uuid>", ... } }

Segurança: valida o header X-Autentique-Token contra AUTENTIQUE_WEBHOOK_SECRET.
Se o secret não estiver configurado, aceita qualquer requisição (útil em dev).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.player import Player
from app.services import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autentique", tags=["autentique"])

_EVENTOS_ASSINATURA = {"document.finished", "document_finished"}


@router.post("/webhook")
async def autentique_webhook(
    request: Request,
    token: str | None = None,
    x_autentique_token: str | None = Header(None),
):
    # Valida token via query param (?token=...) ou header X-Autentique-Token
    secret = settings.AUTENTIQUE_WEBHOOK_SECRET
    if secret:
        received = token or x_autentique_token
        if received != secret:
            raise HTTPException(403, "Token inválido")

    payload = await request.json()
    logger.info("Autentique webhook payload completo: %s", payload)

    # Autentique envia: {"event": {"id": "...", "data": {"id": "<doc_id>", ...}}}
    # O tipo do evento é implícito (só assinamos document.finished neste endpoint)
    raw_event = payload.get("event") or {}
    if isinstance(raw_event, dict):
        event_data = raw_event.get("data") or {}
        doc_id = (
            event_data.get("id")
            or (payload.get("data") or {}).get("id")
            or payload.get("document", {}).get("id")
        )
    else:
        # Fallback: event como string (formato legado)
        evento = raw_event or payload.get("type") or ""
        if evento not in _EVENTOS_ASSINATURA:
            return {"ok": True, "msg": f"evento ignorado: {evento}"}
        data = payload.get("data") or {}
        doc_id = data.get("id") or (data.get("document") or {}).get("id")

    logger.info("Autentique webhook: doc_id=%s", doc_id)
    if not doc_id:
        logger.warning("Autentique webhook sem document id: %s", payload)
        return {"ok": True, "msg": "sem document id"}

    async for db in get_db():
        player = (
            await db.execute(
                select(Player).where(Player.contrato_autentique_id == doc_id)
            )
        ).scalar_one_or_none()

        if not player:
            logger.warning("Autentique webhook: documento %s não vinculado a nenhum jogador", doc_id)
            return {"ok": True, "msg": "jogador não encontrado"}

        if player.contrato_assinado:
            return {"ok": True, "msg": "já assinado"}

        player.contrato_assinado = True
        player.contrato_assinado_em = datetime.now(timezone.utc)

        # Se pagamento já confirmado → ativa subscription e ATIVO; senão → PAGAMENTO
        from app.models.payment import Payment, StatusPagamento
        from app.models.subscription import Subscription, StatusAssinatura
        pay_result = await db.execute(
            select(Payment)
            .join(Subscription, Payment.subscription_id == Subscription.id)
            .where(
                Subscription.player_id == player.id,
                Payment.status == StatusPagamento.PAGO,
            )
        )
        pago = pay_result.scalar_one_or_none()
        if pago and pago.subscription_id:
            sub = await db.get(Subscription, pago.subscription_id)
            if sub and sub.status == StatusAssinatura.PENDENTE:
                sub.status = StatusAssinatura.ATIVA
            player.status = "ativo"
        else:
            player.status = "pagamento"

        await db.commit()

        logger.info("Contrato assinado: player_id=%s nome=%s", player.id, player.nome)

        # Notifica o jogador por e-mail
        try:
            await email_service.enviar_contrato_assinado(player.nome, player.email)
        except Exception as exc:
            logger.error("Erro ao enviar e-mail de contrato assinado: %s", exc)

    return {"ok": True}
