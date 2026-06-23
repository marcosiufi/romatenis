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
    x_autentique_token: str | None = Header(None),
):
    # Validação do token (opcional: só verifica se configurado)
    secret = settings.AUTENTIQUE_WEBHOOK_SECRET
    if secret and x_autentique_token != secret:
        raise HTTPException(403, "Token inválido")

    payload = await request.json()
    evento = payload.get("event") or payload.get("type") or ""
    logger.info("Autentique webhook recebido: evento=%s", evento)

    if evento not in _EVENTOS_ASSINATURA:
        return {"ok": True, "msg": "evento ignorado"}

    # Extrai o ID do documento
    data = payload.get("data") or {}
    doc_id = data.get("id") or (data.get("document") or {}).get("id")
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
        await db.commit()

        logger.info("Contrato assinado: player_id=%s nome=%s", player.id, player.nome)

        # Notifica o jogador por e-mail
        try:
            await email_service.enviar_contrato_assinado(player.nome, player.email)
        except Exception as exc:
            logger.error("Erro ao enviar e-mail de contrato assinado: %s", exc)

    return {"ok": True}
