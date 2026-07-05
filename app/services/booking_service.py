"""
BookingService — toda a lógica de negócio de agendamento.

Janelas do ranking (horário de Brasília):
  Seg–Sex:  06:00–08:00  e  17:00–22:00
  Sábado:   06:00–22:00
  Dom/fer:  06:00–12:00

Horário comercial (seg–sex 08:00–17:00): reservado para aulas/locação.
  Jogadores do ranking só podem reservar nesse intervalo com < 1h de antecedência,
  se o slot ainda estiver livre.

Regras de antecedência (ranking):
  ≥ 6h → reserva normal
  < 1h → janela de última hora (qualquer slot livre, incluindo comercial)
  entre 1h e 6h → bloqueado

Limites semanais (seg–dom):
  Simples: 3 jogos/semana
  Duplas:  2 jogos/semana
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.configuracao import Configuracao
from app.models.feriado import Feriado
from app.models.horario_especial import HorarioEspecial
from app.models.match import LadoPartida, Match, MatchParticipant, StatusPartida, TipoPartida
from app.models.slot_ranking import SlotRanking
from app.models.player import Player
from app.models.season import Season, StatusTemporada
from app.models.subscription import StatusAssinatura, Subscription
from app.schemas.booking import JogadorSlot, SlotDisponivel
from app.services.whatsapp_service import WhatsAppService

FUSO_BR = ZoneInfo("America/Sao_Paulo")


class BookingError(ValueError):
    """Violação de regra de negócio de agendamento."""


# ── Helpers de janela horária (operam em datetime local BR) ──────────────────

def _em_janela_ranking(dt_local: datetime, is_feriado: bool) -> bool:
    wd = dt_local.weekday()  # 0=seg … 6=dom
    t = dt_local.time()
    if wd == 6 or is_feriado:
        return time(6, 0) <= t < time(12, 0)
    if wd == 5:
        return time(6, 0) <= t < time(22, 0)
    # Seg–Sex: duas janelas
    return (time(6, 0) <= t < time(8, 0)) or (time(17, 0) <= t < time(22, 0))


def _em_zona_comercial(dt_local: datetime, is_feriado: bool) -> bool:
    """08:00–17:00 seg–sex (não feriado) — reservado para aulas/locação."""
    return (
        dt_local.weekday() < 5
        and not is_feriado
        and time(8, 0) <= dt_local.time() < time(17, 0)
    )


# ── Service ──────────────────────────────────────────────────────────────────

class BookingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Consultas ─────────────────────────────────────────────────────────────

    async def listar_slots(
        self,
        data: date,
        player: Player,
        tipo: TipoPartida,
    ) -> list[SlotDisponivel]:
        """Retorna todos os slots de 1h para a data (06:00–22:00 BR)."""
        agora = datetime.now(timezone.utc)
        is_feriado = await self._is_feriado(data)
        horario_esp = await self._get_horario_especial(data)
        slots: list[SlotDisponivel] = []

        # Quadra fechada no horário especial → nenhum slot
        if horario_esp and horario_esp.fechado:
            return []

        # Pré-busca todos os bookings confirmados do dia com seus participantes
        dt_dia_inicio = datetime(data.year, data.month, data.day, 0, 0, 0, tzinfo=FUSO_BR).astimezone(timezone.utc)
        dt_dia_fim = dt_dia_inicio + timedelta(days=1)
        res = await self.db.execute(
            select(Booking)
            .options(
                selectinload(Booking.match)
                .selectinload(Match.participantes)
                .selectinload(MatchParticipant.player)
            )
            .where(
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio >= dt_dia_inicio,
                Booking.data_hora_inicio < dt_dia_fim,
            )
        )
        bookings_do_dia: dict[datetime, Booking] = {b.data_hora_inicio: b for b in res.scalars().all()}

        # Slots de ranking configurados para o dia da semana (0=seg, 6=dom)
        dia_semana = datetime(data.year, data.month, data.day).weekday()
        slots_ranking_dia = await self._get_slots_ranking_dia(dia_semana)

        # Intervalo de horas: usa horário especial se definido, senão padrão 6–22
        h_ini = horario_esp.hora_abertura if horario_esp and horario_esp.hora_abertura is not None else 6
        h_fim = horario_esp.hora_fechamento if horario_esp and horario_esp.hora_fechamento is not None else 22

        for hora in range(h_ini, h_fim):
            dt_local = datetime(data.year, data.month, data.day, hora, 0, 0, tzinfo=FUSO_BR)
            dt_utc = dt_local.astimezone(timezone.utc)
            dt_fim_utc = dt_utc + timedelta(hours=1)

            # Janela de ranking: usa SlotRanking cadastrado; fallback para lógica hardcoded
            if slots_ranking_dia:
                em_janela = self._hora_em_slots_ranking(hora, slots_ranking_dia)
            else:
                em_janela = _em_janela_ranking(dt_local, is_feriado)

            # Horas fora do ranking dentro do horário especial → comercial (última hora)
            if horario_esp:
                em_comercial = not em_janela
            else:
                em_comercial = not em_janela and _em_zona_comercial(dt_local, is_feriado)

            if not em_janela and not em_comercial:
                continue

            antecedencia = dt_utc - agora

            if antecedencia.total_seconds() <= 0:
                slots.append(SlotDisponivel(
                    data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                    disponivel=False, tipo_disponibilidade="passado",
                    motivo_indisponibilidade="Horário já passou",
                    **self._extrair_info_booking(bookings_do_dia.get(dt_utc)),
                ))
                continue

            booking_ocupado = bookings_do_dia.get(dt_utc)
            if booking_ocupado is not None:
                slots.append(SlotDisponivel(
                    data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                    disponivel=False, tipo_disponibilidade="ocupado",
                    motivo_indisponibilidade="Horário já reservado",
                    **self._extrair_info_booking(booking_ocupado),
                ))
                continue

            if em_comercial:
                if antecedencia > timedelta(hours=1):
                    slots.append(SlotDisponivel(
                        data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                        disponivel=False, tipo_disponibilidade="comercial",
                        motivo_indisponibilidade="Disponível apenas na última hora",
                    ))
                else:
                    slots.append(SlotDisponivel(
                        data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                        disponivel=True, tipo_disponibilidade="comercial_ultima_hora",
                    ))
                continue

            # Janela de ranking: 6h normal OU última hora; entre 1h–6h é bloqueado
            if timedelta(hours=1) < antecedencia < timedelta(hours=6):
                slots.append(SlotDisponivel(
                    data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                    disponivel=False, tipo_disponibilidade="janela_morta",
                    motivo_indisponibilidade="Reserve com 6h ou mais de antecedência ou na última hora",
                ))
            elif antecedencia <= timedelta(hours=1):
                slots.append(SlotDisponivel(
                    data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                    disponivel=True, tipo_disponibilidade="ranking_ultima_hora",
                ))
            else:
                slots.append(SlotDisponivel(
                    data_hora_inicio=dt_utc, data_hora_fim=dt_fim_utc,
                    disponivel=True, tipo_disponibilidade="ranking",
                ))

        return slots

    async def listar_reservas(
        self,
        player: Player,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> list[Booking]:
        q = select(Booking).order_by(Booking.data_hora_inicio)
        if not player.is_admin:
            q = q.where(Booking.jogador_responsavel_id == player.id)
        if data_inicio:
            dt = datetime(data_inicio.year, data_inicio.month, data_inicio.day, tzinfo=timezone.utc)
            q = q.where(Booking.data_hora_inicio >= dt)
        if data_fim:
            dt = datetime(data_fim.year, data_fim.month, data_fim.day, tzinfo=timezone.utc) + timedelta(days=1)
            q = q.where(Booking.data_hora_inicio < dt)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ── Criação ───────────────────────────────────────────────────────────────

    async def criar_reserva_ranking(
        self,
        player: Player,
        data_hora: datetime,
        tipo: TipoPartida,
        lado_a: list[int],
        lado_b: list[int],
    ) -> tuple[Booking, Match]:
        await self._validar_slot_ranking(player, data_hora, tipo, lado_a, lado_b)

        # Temporada ativa (opcional — partida pode existir sem temporada)
        res = await self.db.execute(select(Season).where(Season.status == StatusTemporada.ATIVA))
        season = res.scalar_one_or_none()

        match = Match(
            tipo=tipo,
            data_hora=data_hora,
            status=StatusPartida.AGENDADO,
            season_id=season.id if season else None,
        )
        self.db.add(match)
        await self.db.flush()

        for pid in lado_a:
            self.db.add(MatchParticipant(match_id=match.id, player_id=pid, lado=LadoPartida.A))
        for pid in lado_b:
            self.db.add(MatchParticipant(match_id=match.id, player_id=pid, lado=LadoPartida.B))

        booking = Booking(
            data_hora_inicio=data_hora,
            data_hora_fim=data_hora + timedelta(hours=1),
            tipo=TipoReserva.RANKING,
            status=StatusReserva.CONFIRMADA,
            jogador_responsavel_id=player.id,
            match_id=match.id,
        )
        self.db.add(booking)
        await self.db.commit()
        await self.db.refresh(booking)
        await self.db.refresh(match)
        await self._notificar_reserva(match, lado_a, lado_b)
        return booking, match

    async def criar_locacao_avulsa(
        self,
        data_hora: datetime,
        player: Player | None = None,
        nome_externo: str | None = None,
        telefone_externo: str | None = None,
    ) -> Booking:
        agora = datetime.now(timezone.utc)
        if data_hora <= agora:
            raise BookingError("Não é possível reservar no passado")
        if await self._slot_ocupado(data_hora):
            raise BookingError("Horário já ocupado")

        booking = Booking(
            data_hora_inicio=data_hora,
            data_hora_fim=data_hora + timedelta(hours=1),
            tipo=TipoReserva.LOCACAO_AVULSA,
            status=StatusReserva.CONFIRMADA,
            jogador_responsavel_id=player.id if player else None,
            cliente_locacao_nome=nome_externo,
            cliente_locacao_telefone=telefone_externo,
            valor=float((await Configuracao.get(self.db)).preco_locacao_hora),
        )
        self.db.add(booking)
        await self.db.commit()
        await self.db.refresh(booking)
        return booking

    async def cancelar_reserva(self, booking_id: int, player: Player) -> Booking:
        booking = await self.db.get(Booking, booking_id)
        if booking is None:
            raise BookingError("Reserva não encontrada")
        if not player.is_admin and booking.jogador_responsavel_id != player.id:
            raise BookingError("Sem permissão para cancelar esta reserva")

        agora = datetime.now(timezone.utc)
        if booking.data_hora_inicio <= agora:
            raise BookingError("Não é possível cancelar reservas passadas ou em andamento")

        booking.status = StatusReserva.CANCELADA
        if booking.match_id:
            match = await self.db.get(Match, booking.match_id)
            if match and match.status == StatusPartida.AGENDADO:
                match.status = StatusPartida.CANCELADO_SEM_PLACAR

        await self.db.commit()
        await self.db.refresh(booking)
        return booking

    # ── Validações privadas ───────────────────────────────────────────────────

    async def _validar_slot_ranking(
        self,
        player: Player,
        data_hora: datetime,
        tipo: TipoPartida,
        lado_a: list[int],
        lado_b: list[int],
    ) -> None:
        agora = datetime.now(timezone.utc)

        if data_hora <= agora:
            raise BookingError("Não é possível reservar no passado")

        dt_local = data_hora.astimezone(FUSO_BR)
        horario_esp = await self._get_horario_especial(dt_local.date())

        if horario_esp and horario_esp.fechado:
            raise BookingError("Quadra fechada neste dia")

        dia_semana = dt_local.weekday()
        slots_ranking_dia = await self._get_slots_ranking_dia(dia_semana)

        if horario_esp:
            h_ini = horario_esp.hora_abertura if horario_esp.hora_abertura is not None else 6
            h_fim = horario_esp.hora_fechamento if horario_esp.hora_fechamento is not None else 22
            if not (h_ini <= dt_local.hour < h_fim):
                raise BookingError("Horário fora do período especial do dia")
            if slots_ranking_dia and not self._hora_em_slots_ranking(dt_local.hour, slots_ranking_dia):
                raise BookingError("Horário fora das janelas de ranking configuradas")
            em_comercial = False
        else:
            is_feriado = await self._is_feriado(dt_local.date())
            if slots_ranking_dia:
                em_janela = self._hora_em_slots_ranking(dt_local.hour, slots_ranking_dia)
                em_comercial = not em_janela and _em_zona_comercial(dt_local, is_feriado)
            else:
                em_janela = _em_janela_ranking(dt_local, is_feriado)
                em_comercial = _em_zona_comercial(dt_local, is_feriado)
            if not em_janela and not em_comercial:
                raise BookingError("Horário fora das janelas disponíveis para o ranking")

        antecedencia = data_hora - agora

        if em_comercial:
            if antecedencia > timedelta(hours=1):
                raise BookingError(
                    "Horário comercial (seg–sex 08h–17h) disponível apenas na janela "
                    "de última hora (menos de 1h de antecedência)"
                )
        elif timedelta(hours=1) < antecedencia < timedelta(hours=6):
            raise BookingError(
                "Fora da janela de reserva: reserve com no mínimo 6h de antecedência "
                "ou na janela de última hora (menos de 1h do início)"
            )

        if not player.contrato_assinado:
            raise BookingError("Assine o Termo de Adesão para reservar quadra")

        if not await self._tem_assinatura_ativa(player.id):
            raise BookingError("Assinatura inativa")

        esperado = 1 if tipo == TipoPartida.SIMPLES else 2
        if len(lado_a) != esperado or len(lado_b) != esperado:
            raise BookingError(f"Partida de {tipo.value} requer {esperado} jogador(es) por lado")

        if player.id not in lado_a:
            raise BookingError("Você deve estar no Lado A da partida")

        todos = lado_a + lado_b
        if len(todos) != len(set(todos)):
            raise BookingError("O mesmo jogador não pode estar em ambos os lados")

        for pid in todos:
            await self._verificar_limite_ativo(pid, tipo)
            await self._verificar_limite_semanal(pid, tipo, data_hora)

        if await self._slot_ocupado(data_hora):
            raise BookingError("Horário já reservado")

    async def _is_feriado(self, data: date) -> bool:
        result = await self.db.execute(
            select(Feriado).where(
                or_(
                    Feriado.data == data,
                    and_(
                        Feriado.recorrente.is_(True),
                        extract("month", Feriado.data) == data.month,
                        extract("day", Feriado.data) == data.day,
                    ),
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def _tem_assinatura_ativa(self, player_id: int) -> bool:
        agora = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.player_id == player_id,
                Subscription.status == StatusAssinatura.ATIVA,
                Subscription.data_expiracao > agora,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _verificar_limite_semanal(
        self, player_id: int, tipo: TipoPartida, data_hora: datetime
    ) -> None:
        """Conta partidas confirmadas do tipo na semana (seg–dom) do slot."""
        dt_local = data_hora.astimezone(FUSO_BR)
        inicio_local = (dt_local - timedelta(days=dt_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fim_local = inicio_local + timedelta(days=7)
        inicio_utc = inicio_local.astimezone(timezone.utc)
        fim_utc = fim_local.astimezone(timezone.utc)

        result = await self.db.execute(
            select(func.count(MatchParticipant.id))
            .join(Match, MatchParticipant.match_id == Match.id)
            .join(Booking, Match.id == Booking.match_id)
            .where(
                MatchParticipant.player_id == player_id,
                Match.tipo == tipo,
                Match.status != StatusPartida.CANCELADO_SEM_PLACAR,
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio >= inicio_utc,
                Booking.data_hora_inicio < fim_utc,
            )
        )
        count: int = result.scalar() or 0
        limite = 3 if tipo == TipoPartida.SIMPLES else 2
        if count >= limite:
            raise BookingError(
                f"Limite semanal atingido: máximo de {limite} jogo(s) de "
                f"{tipo.value} por semana (já agendados nesta semana: {count})"
            )

    async def _verificar_limite_ativo(self, player_id: int, tipo: TipoPartida) -> None:
        """Bloqueia se o jogador já tem 1 partida deste tipo agendada e ainda não encerrada."""
        agora = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(func.count(MatchParticipant.id))
            .join(Match, MatchParticipant.match_id == Match.id)
            .join(Booking, Match.id == Booking.match_id)
            .where(
                MatchParticipant.player_id == player_id,
                Match.tipo == tipo,
                Match.status == StatusPartida.AGENDADO,
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_fim > agora,
            )
        )
        if (result.scalar() or 0) >= 1:
            nome = "simples" if tipo == TipoPartida.SIMPLES else "duplas"
            raise BookingError(
                f"Você já tem uma partida de {nome} agendada. "
                f"Aguarde o encerramento do jogo atual para marcar outro."
            )

    async def _get_horario_especial(self, data: date) -> "HorarioEspecial | None":
        res = await self.db.execute(
            select(HorarioEspecial).where(HorarioEspecial.data == data)
        )
        return res.scalar_one_or_none()

    async def _get_slots_ranking_dia(self, dia_semana: int) -> list[SlotRanking]:
        res = await self.db.execute(
            select(SlotRanking).where(
                SlotRanking.dia_semana == dia_semana,
                SlotRanking.ativo.is_(True),
            )
        )
        return list(res.scalars().all())

    @staticmethod
    def _hora_em_slots_ranking(hora: int, slots: list[SlotRanking]) -> bool:
        from datetime import time as time_
        t = time_(hora, 0)
        return any(s.hora_inicio <= t < s.hora_fim for s in slots)

    def _extrair_info_booking(self, booking: "Booking | None") -> dict:
        """Extrai jogadores, placar e status de um booking para popular o SlotDisponivel."""
        if not booking or not booking.match:
            return {}
        m = booking.match
        jogadores = [
            JogadorSlot(
                nome=p.player.nome if p.player else "?",
                apelido=p.player.apelido if p.player else None,
                lado=p.lado.value,
            )
            for p in m.participantes
            if p.player
        ]
        return {
            "jogadores": jogadores,
            "placar": m.placar,
            "lado_vencedor": m.lado_vencedor,
            "status_partida": m.status.value,
        }

    async def _slot_ocupado(self, dt_inicio: datetime) -> bool:
        dt_fim = dt_inicio + timedelta(hours=1)
        result = await self.db.execute(
            select(Booking).where(
                Booking.status == StatusReserva.CONFIRMADA,
                Booking.data_hora_inicio < dt_fim,
                Booking.data_hora_fim > dt_inicio,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _notificar_reserva(
        self, match: Match, lado_a: list[int], lado_b: list[int]
    ) -> None:
        try:
            todos_ids = lado_a + lado_b
            res = await self.db.execute(select(Player).where(Player.id.in_(todos_ids)))
            by_id = {p.id: p for p in res.scalars().all()}
            wa = WhatsAppService(self.db)

            for pid in lado_a:
                p = by_id.get(pid)
                if not p:
                    continue
                adv = " / ".join(by_id[bid].nome.split()[0] for bid in lado_b if bid in by_id)
                await wa.notificar_reserva_confirmada(p.id, p.nome, p.telefone, adv, match.data_hora, match.tipo.value)

            for pid in lado_b:
                p = by_id.get(pid)
                if not p:
                    continue
                adv = " / ".join(by_id[aid].nome.split()[0] for aid in lado_a if aid in by_id)
                await wa.notificar_reserva_confirmada(p.id, p.nome, p.telefone, adv, match.data_hora, match.tipo.value)
        except Exception:
            pass
