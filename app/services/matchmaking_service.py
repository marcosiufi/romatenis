"""
Algoritmo de matchmaking: encontra jogadores elegíveis para slots livres e envia convites.

Fluxo:
  1. admin POST /matchmaking/executar?data=YYYY-MM-DD&tipo=simples|duplas
  2. MatchmakingService.executar() varre os slots livres do dia.
  3. Para cada slot, busca jogadores elegíveis (assinatura ativa, dentro do limite semanal,
     sem jogo naquele horário, com aceita_convites_sistema = True).
  4. Emparelha por rating (interleaving top-rated) e cria MatchInvitation + MatchInvitationPlayer.
  5. Envia convite WhatsApp via N8N.
  6. N8N chama POST /webhooks/n8n/reply quando o jogador responde.
  7. MatchmakingService.processar_resposta() atualiza o status e, se todos aceitaram,
     cria Booking + Match e envia confirmação.
"""

import datetime as dt_mod
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSession
from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.match import LadoPartida, Match, MatchParticipant, StatusPartida, TipoPartida
from app.models.match_invitation import (
    MatchInvitation,
    MatchInvitationPlayer,
    StatusConvite,
    StatusRodadaMatchmaking,
)
from app.models.player import Player
from app.models.season import Season, StatusTemporada
from app.models.subscription import StatusAssinatura, Subscription
from app.services.whatsapp_service import WhatsAppService

FUSO_BR = ZoneInfo("America/Sao_Paulo")
LIMITE_SEMANAL = {TipoPartida.SIMPLES: 3, TipoPartida.DUPLAS: 2}
JOGADORES_POR_LADO = {TipoPartida.SIMPLES: 1, TipoPartida.DUPLAS: 2}


class MatchmakingError(ValueError):
    pass


class MatchmakingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._wa = WhatsAppService(db)

    # ── Execução ──────────────────────────────────────────────────────────────

    async def executar(self, data: str, tipo: TipoPartida) -> dict:
        data_obj = dt_mod.date.fromisoformat(data)
        slots = await self._slots_livres(data_obj)

        convites_enviados = 0
        slots_sem_jogadores = 0

        for slot_dt in slots:
            if slot_dt < datetime.now(timezone.utc):
                continue
            if await self._tem_convite_ativo(slot_dt, tipo):
                continue

            elegíveis = await self._jogadores_elegiveis(slot_dt, tipo)
            necessario = JOGADORES_POR_LADO[tipo] * 2

            if len(elegíveis) < necessario:
                slots_sem_jogadores += 1
                continue

            lados = self._emparelhar(elegíveis, tipo)
            if not lados:
                slots_sem_jogadores += 1
                continue

            await self._criar_e_enviar_convite(slot_dt, tipo, lados["A"], lados["B"])
            convites_enviados += 1

        return {
            "data": data,
            "tipo": tipo.value,
            "slots_livres": len(slots),
            "convites_enviados": convites_enviados,
            "slots_sem_jogadores": slots_sem_jogadores,
        }

    # ── Resposta do jogador ───────────────────────────────────────────────────

    async def processar_resposta(self, wamid_convite: str, aceita: bool) -> dict:
        result = await self.db.execute(
            select(MatchInvitationPlayer)
            .where(MatchInvitationPlayer.wamid_convite == wamid_convite)
            .options(
                selectinload(MatchInvitationPlayer.invitation).selectinload(
                    MatchInvitation.jogadores
                )
            )
        )
        inv_player = result.scalar_one_or_none()
        if not inv_player:
            return {"processado": False, "motivo": "Convite não encontrado"}

        inv = inv_player.invitation
        if inv.status != StatusRodadaMatchmaking.AGUARDANDO:
            return {"processado": False, "motivo": f"Rodada já encerrada ({inv.status.value})"}

        if datetime.now(timezone.utc) > inv.expira_em:
            inv.status = StatusRodadaMatchmaking.FALHOU
            inv_player.status = StatusConvite.EXPIRADO
            await self.db.commit()
            return {"processado": False, "motivo": "Convite expirado"}

        inv_player.respondido_em = datetime.now(timezone.utc)

        if not aceita:
            inv_player.status = StatusConvite.RECUSADO
            inv.status = StatusRodadaMatchmaking.FALHOU
            for jp in inv.jogadores:
                if jp.id != inv_player.id and jp.status == StatusConvite.PENDENTE:
                    jp.status = StatusConvite.CANCELADO
            await self.db.commit()
            return {"processado": True, "resultado": "recusado"}

        inv_player.status = StatusConvite.CONFIRMADO
        todos_confirmados = all(jp.status == StatusConvite.CONFIRMADO for jp in inv.jogadores)

        if todos_confirmados:
            # Snapshot de tudo antes de qualquer commit (evita lazy-load pós-commit em async)
            jogadores_snap = [(jp.player_id, jp.lado_proposto) for jp in inv.jogadores]
            slot_dt = inv.slot_data_hora
            tipo_jogo = inv.tipo

            booking, _ = await self._criar_booking(inv)
            inv.status = StatusRodadaMatchmaking.CONFIRMADA
            inv.booking_id = booking.id
            await self.db.commit()

            await self._notificar_confirmacao(jogadores_snap, slot_dt, tipo_jogo)
            return {"processado": True, "resultado": "confirmado", "booking_id": booking.id}

        await self.db.commit()
        return {"processado": True, "resultado": "aguardando_outros"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _slots_livres(self, data: dt_mod.date) -> list[datetime]:
        inicio = datetime(data.year, data.month, data.day, 6, 0, tzinfo=FUSO_BR)
        fim = datetime(data.year, data.month, data.day, 22, 0, tzinfo=FUSO_BR)

        todos_slots: list[datetime] = []
        cur = inicio
        while cur < fim:
            todos_slots.append(cur)
            cur += timedelta(hours=1)

        result = await self.db.execute(
            select(Booking.data_hora_inicio).where(
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio >= inicio,
                Booking.data_hora_inicio < fim,
            )
        )
        ocupados = {row[0] for row in result}
        return [s for s in todos_slots if s not in ocupados]

    async def _tem_convite_ativo(self, slot_dt: datetime, tipo: TipoPartida) -> bool:
        result = await self.db.execute(
            select(MatchInvitation.id).where(
                MatchInvitation.slot_data_hora == slot_dt,
                MatchInvitation.tipo == tipo,
                MatchInvitation.status == StatusRodadaMatchmaking.AGUARDANDO,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _jogadores_elegiveis(
        self, slot_dt: datetime, tipo: TipoPartida
    ) -> list[Player]:
        agora = datetime.now(timezone.utc)
        sem_ini, sem_fim = _semana(slot_dt)
        limite = LIMITE_SEMANAL[tipo]
        slot_fim = slot_dt + timedelta(hours=1)

        result = await self.db.execute(
            select(Player).where(
                Player.aceita_convites_sistema == True,  # noqa: E712
                Player.status == "ativo",
            )
        )
        candidatos = list(result.scalars().all())

        elegiveis: list[Player] = []
        for player in candidatos:
            sub = await self.db.execute(
                select(Subscription.id).where(
                    Subscription.player_id == player.id,
                    Subscription.status == StatusAssinatura.ATIVA,
                    Subscription.data_expiracao > agora,
                )
            )
            if not sub.scalar_one_or_none():
                continue

            ocupado = await self.db.execute(
                select(Booking.id)
                .join(Match, Booking.match_id == Match.id)
                .join(MatchParticipant, Match.id == MatchParticipant.match_id)
                .where(
                    MatchParticipant.player_id == player.id,
                    Booking.status == StatusReserva.CONFIRMADA,
                    Booking.data_hora_inicio >= slot_dt,
                    Booking.data_hora_inicio < slot_fim,
                )
            )
            if ocupado.scalar_one_or_none():
                continue

            contagem = await self.db.execute(
                select(Booking.id)
                .join(Match, Booking.match_id == Match.id)
                .join(MatchParticipant, Match.id == MatchParticipant.match_id)
                .where(
                    MatchParticipant.player_id == player.id,
                    Match.tipo == tipo,
                    Booking.status == StatusReserva.CONFIRMADA,
                    Booking.data_hora_inicio >= sem_ini,
                    Booking.data_hora_inicio < sem_fim,
                )
            )
            if len(contagem.all()) >= limite:
                continue

            elegiveis.append(player)

        return sorted(elegiveis, key=lambda p: p.rating_atual, reverse=True)

    def _emparelhar(
        self, players: list[Player], tipo: TipoPartida
    ) -> dict[str, list[Player]] | None:
        n = JOGADORES_POR_LADO[tipo]
        if len(players) < n * 2:
            return None
        top = players[: n * 2]
        # Interleave: 1º e 3º vs 2º e 4º → lados mais equilibrados por rating
        lado_a = [top[i] for i in range(0, n * 2, 2)]
        lado_b = [top[i] for i in range(1, n * 2, 2)]
        return {"A": lado_a, "B": lado_b}

    async def _criar_e_enviar_convite(
        self,
        slot_dt: datetime,
        tipo: TipoPartida,
        lado_a: list[Player],
        lado_b: list[Player],
    ) -> MatchInvitation:
        expira_em = slot_dt - timedelta(hours=2)
        if expira_em < datetime.now(timezone.utc):
            expira_em = datetime.now(timezone.utc) + timedelta(minutes=30)

        inv = MatchInvitation(tipo=tipo, slot_data_hora=slot_dt, expira_em=expira_em)
        self.db.add(inv)
        await self.db.flush()

        # Lista de (player, lado, MatchInvitationPlayer) para envio posterior
        registros: list[tuple[Player, str, MatchInvitationPlayer]] = []
        for player, lado in [(p, "A") for p in lado_a] + [(p, "B") for p in lado_b]:
            ip = MatchInvitationPlayer(
                invitation_id=inv.id, player_id=player.id, lado_proposto=lado
            )
            self.db.add(ip)
            registros.append((player, lado, ip))

        await self.db.flush()

        # Envia convites — cada _enviar faz flush+commit internamente (log WhatsApp)
        for player, lado, ip in registros:
            adversarios = " / ".join(
                p.nome.split()[0] for p, l, _ in registros if l != lado
            )
            wamid = await self._wa.enviar_convite_matchmaking(
                player_id=player.id,
                nome=player.nome,
                telefone=player.telefone,
                adversario=adversarios,
                data_hora=slot_dt,
                tipo_jogo=tipo.value,
                invitation_player_id=ip.id,
            )
            if wamid:
                ip.wamid_convite = wamid

        await self.db.commit()
        return inv

    async def _criar_booking(
        self, inv: MatchInvitation
    ) -> tuple[Booking, Match]:
        season_result = await self.db.execute(
            select(Season.id)
            .where(Season.status == StatusTemporada.ATIVA)
            .order_by(Season.id.desc())
        )
        season_id = season_result.scalar_one_or_none()

        match = Match(
            tipo=inv.tipo,
            status=StatusPartida.AGENDADO,
            data_hora=inv.slot_data_hora,
            season_id=season_id,
        )
        self.db.add(match)
        await self.db.flush()

        for jp in inv.jogadores:
            self.db.add(
                MatchParticipant(
                    match_id=match.id,
                    player_id=jp.player_id,
                    lado=LadoPartida.A if jp.lado_proposto == "A" else LadoPartida.B,
                )
            )

        responsavel_id = next(jp.player_id for jp in inv.jogadores if jp.lado_proposto == "A")
        booking = Booking(
            jogador_responsavel_id=responsavel_id,
            match_id=match.id,
            tipo=TipoReserva.RANKING,
            status=StatusReserva.CONFIRMADA,
            data_hora_inicio=inv.slot_data_hora,
            data_hora_fim=inv.slot_data_hora + timedelta(hours=1),
        )
        self.db.add(booking)
        await self.db.flush()
        return booking, match

    async def _notificar_confirmacao(
        self,
        jogadores_snap: list[tuple[int, str]],
        slot_dt: datetime,
        tipo: TipoPartida,
    ) -> None:
        """Envia confirmação a todos os jogadores usando snapshot pré-commit."""
        player_ids = [pid for pid, _ in jogadores_snap]
        result = await self.db.execute(select(Player).where(Player.id.in_(player_ids)))
        by_id = {p.id: p for p in result.scalars().all()}

        for player_id, lado in jogadores_snap:
            player = by_id.get(player_id)
            if not player:
                continue
            adversarios = " / ".join(
                by_id[pid].nome.split()[0]
                for pid, l in jogadores_snap
                if l != lado and pid in by_id
            )
            try:
                await self._wa.notificar_reserva_confirmada(
                    player_id=player.id,
                    nome=player.nome,
                    telefone=player.telefone,
                    adversario=adversarios,
                    data_hora=slot_dt,
                    tipo_jogo=tipo.value,
                )
            except Exception:
                pass


def _semana(dt: datetime) -> tuple[datetime, datetime]:
    local = dt.astimezone(FUSO_BR)
    inicio = local - timedelta(days=local.weekday())
    inicio_sem = datetime(inicio.year, inicio.month, inicio.day, 0, 0, tzinfo=FUSO_BR)
    return inicio_sem, inicio_sem + timedelta(weeks=1)
