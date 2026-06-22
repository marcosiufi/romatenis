"""
Serviço de notificações WhatsApp via N8N.

O backend NÃO chama a API da Meta diretamente: envia eventos HTTP para o N8N,
que gerencia os templates aprovados, filas de envio e retentativas.

Formato do evento enviado ao N8N:
  POST {N8N_EVENTS_WEBHOOK_URL}
  Headers: X-N8N-Secret: {N8N_SECRET}
  Body: {
    "tipo": "<tipo_mensagem>",
    "jogador": {"id": int, "nome": str, "telefone": str},
    "dados": { ... }   ← campos específicos por tipo
  }

O N8N responde com {"wamid": "<id_mensagem>"} após enviar via WhatsApp Cloud API.
"""

import httpx

from app.core.config import settings
from app.core.database import AsyncSession
from app.models.whatsapp_log import StatusEnvio, TipoMensagem, WhatsAppMessageLog


class WhatsAppService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Notificações de agendamento ───────────────────────────────────────────

    async def notificar_reserva_confirmada(
        self,
        player_id: int,
        nome: str,
        telefone: str,
        adversario: str,
        data_hora,
        tipo_jogo: str,
    ) -> None:
        await self._enviar(
            player_id,
            TipoMensagem.CONFIRMACAO_RESERVA,
            {
                "tipo": "confirmacao_reserva",
                "jogador": {"id": player_id, "nome": nome, "telefone": telefone},
                "dados": {
                    "adversario": adversario,
                    "data_hora": data_hora.isoformat(),
                    "tipo_jogo": tipo_jogo,
                },
            },
        )

    async def solicitar_placar(
        self,
        player_id: int,
        nome: str,
        telefone: str,
        adversario: str,
        data_hora,
        match_id: int,
    ) -> None:
        await self._enviar(
            player_id,
            TipoMensagem.SOLICITACAO_PLACAR,
            {
                "tipo": "solicitacao_placar",
                "jogador": {"id": player_id, "nome": nome, "telefone": telefone},
                "dados": {
                    "adversario": adversario,
                    "data_hora": data_hora.isoformat(),
                    "match_id": match_id,
                },
            },
        )

    async def notificar_resultado(
        self,
        player_id: int,
        nome: str,
        telefone: str,
        adversario: str,
        placar: str,
        ganhou: bool,
        pontos_delta: int,
    ) -> None:
        await self._enviar(
            player_id,
            TipoMensagem.RESULTADO_RATING,
            {
                "tipo": "resultado_rating",
                "jogador": {"id": player_id, "nome": nome, "telefone": telefone},
                "dados": {
                    "adversario": adversario,
                    "placar": placar,
                    "ganhou": ganhou,
                    "pontos_delta": pontos_delta,
                },
            },
        )

    async def notificar_aviso_expiracao(
        self,
        player_id: int,
        nome: str,
        telefone: str,
        data_expiracao,
        dias_restantes: int,
    ) -> None:
        await self._enviar(
            player_id,
            TipoMensagem.AVISO_EXPIRACAO,
            {
                "tipo": "aviso_expiracao",
                "jogador": {"id": player_id, "nome": nome, "telefone": telefone},
                "dados": {
                    "data_expiracao": data_expiracao.isoformat(),
                    "dias_restantes": dias_restantes,
                },
            },
        )

    # ── Matchmaking ───────────────────────────────────────────────────────────

    async def enviar_convite_matchmaking(
        self,
        player_id: int,
        nome: str,
        telefone: str,
        adversario: str,
        data_hora,
        tipo_jogo: str,
        invitation_player_id: int,
    ) -> str | None:
        """Retorna o wamid recebido do N8N (para rastrear respostas)."""
        resultado = await self._enviar(
            player_id,
            TipoMensagem.CONVITE_MATCHMAKING,
            {
                "tipo": "convite_matchmaking",
                "jogador": {"id": player_id, "nome": nome, "telefone": telefone},
                "dados": {
                    "adversario": adversario,
                    "data_hora": data_hora.isoformat(),
                    "tipo_jogo": tipo_jogo,
                    "invitation_player_id": invitation_player_id,
                },
            },
        )
        return resultado.get("wamid") if resultado else None

    # ── Core ──────────────────────────────────────────────────────────────────

    async def _enviar(
        self, player_id: int, tipo: TipoMensagem, payload: dict
    ) -> dict:
        """Registra no log, dispara para N8N e atualiza o status."""
        log = WhatsAppMessageLog(
            player_id=player_id, tipo=tipo, status_envio=StatusEnvio.PENDENTE
        )
        self.db.add(log)
        await self.db.flush()

        if not settings.N8N_EVENTS_WEBHOOK_URL:
            log.status_envio = StatusEnvio.ENVIADO
            await self.db.commit()
            return {}

        try:
            headers = {}
            if settings.N8N_SECRET:
                headers["X-N8N-Secret"] = settings.N8N_SECRET

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    settings.N8N_EVENTS_WEBHOOK_URL, json=payload, headers=headers
                )
                r.raise_for_status()
                data: dict = r.json() if r.content else {}

            log.status_envio = StatusEnvio.ENVIADO
            log.wamid = data.get("wamid")
            await self.db.commit()
            return data

        except Exception:
            log.status_envio = StatusEnvio.FALHOU
            await self.db.commit()
            return {}
