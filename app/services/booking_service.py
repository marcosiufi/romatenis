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

Jogo avulso:
  Membro joga com convidado(s) de fora do ranking. Só pode ser reservado na
  janela de última hora (< 1h), em qualquer slot livre. Gera cobrança por
  convidado e o slot só é confirmado após o pagamento. Não pontua para ninguém,
  mas consome a cota semanal do tipo (simples/duplas) de cada membro envolvido.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.configuracao import Configuracao
from app.models.convidado import Convidado
from app.models.feriado import Feriado
from app.models.horario_especial import HorarioEspecial
from app.models.match import LadoPartida, Match, MatchParticipant, StatusPartida, TipoPartida
from app.models.payment import MetodoPagamento, Payment, StatusPagamento
from app.models.slot_ranking import SlotRanking
from app.models.player import Player
from app.models.season import Season, StatusTemporada
from app.models.subscription import StatusAssinatura, Subscription
from app.schemas.booking import ConvidadoIn, JogadorSlot, SlotDisponivel
from app.services.whatsapp_service import WhatsAppService

FUSO_BR = ZoneInfo("America/Sao_Paulo")

LIMITE_SEMANAL = {TipoPartida.SIMPLES: 3, TipoPartida.DUPLAS: 2}

# Uma pré-reserva não paga segura o slot por este tempo antes de liberá-lo
JANELA_PRE_RESERVA = timedelta(minutes=10)


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
                .selectinload(MatchParticipant.player),
                selectinload(Booking.match)
                .selectinload(Match.participantes)
                .selectinload(MatchParticipant.convidado),
            )
            .where(
                self._filtro_slot_tomado(),
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

    async def criar_jogo_avulso(
        self,
        player: Player,
        data_hora: datetime,
        tipo: TipoPartida,
        membros_a: list[int],
        membros_b: list[int],
        convidados: list[ConvidadoIn],
        metodo_pagamento: str,
    ) -> dict:
        """
        Reserva de última hora entre membros e convidados de fora do ranking.

        A partida não pontua, mas consome a cota semanal de cada membro. O slot
        fica AGUARDANDO_PAGAMENTO e só é confirmado pelo webhook do Asaas.
        """
        await self._validar_jogo_avulso(
            player, data_hora, tipo, membros_a, membros_b, convidados
        )

        cfg = await Configuracao.get(self.db)
        valor = float(cfg.preco_jogo_avulso) * len(convidados)

        match = Match(
            tipo=tipo,
            data_hora=data_hora,
            status=StatusPartida.AGENDADO,
            season_id=None,  # fora da temporada: não pontua
            avulso=True,
        )
        self.db.add(match)
        await self.db.flush()

        for pid in membros_a:
            self.db.add(MatchParticipant(match_id=match.id, player_id=pid, lado=LadoPartida.A))
        for pid in membros_b:
            self.db.add(MatchParticipant(match_id=match.id, player_id=pid, lado=LadoPartida.B))

        for c in convidados:
            convidado = Convidado(
                nome=c.nome.strip(),
                cpf=c.cpf,
                whatsapp=c.whatsapp,
                data_nascimento=c.data_nascimento,
                apelido=c.apelido,
            )
            self.db.add(convidado)
            await self.db.flush()
            self.db.add(MatchParticipant(
                match_id=match.id,
                convidado_id=convidado.id,
                lado=LadoPartida(c.lado),
            ))

        booking = Booking(
            data_hora_inicio=data_hora,
            data_hora_fim=data_hora + timedelta(hours=1),
            tipo=TipoReserva.JOGO_AVULSO,
            status=StatusReserva.AGUARDANDO_PAGAMENTO,
            jogador_responsavel_id=player.id,
            match_id=match.id,
            valor=valor,
        )
        self.db.add(booking)
        await self.db.flush()

        cobranca = await self._cobrar_jogo_avulso(player, booking, valor, metodo_pagamento, data_hora)

        await self.db.commit()
        return {"booking_id": booking.id, "match_id": match.id, "valor": valor, **cobranca}

    async def _cobrar_jogo_avulso(
        self,
        player: Player,
        booking: Booking,
        valor: float,
        metodo_pagamento: str,
        data_hora: datetime,
    ) -> dict:
        """Gera a cobrança no Asaas. Sem cobrança não há reserva — erro aborta tudo."""
        from app.services.asaas_client import AsaasClient

        try:
            asaas = AsaasClient()
            customer_id = player.asaas_customer_id
            if not customer_id:
                customer_id = await asaas.get_or_create_customer(
                    nome=player.nome,
                    email=player.email,
                    telefone=player.telefone,
                    cpf=player.cpf,
                )
                player.asaas_customer_id = customer_id

            dt_local = data_hora.astimezone(FUSO_BR)
            charge = await asaas.criar_cobranca(
                customer_id=customer_id,
                valor=valor,
                billing_type="CREDIT_CARD" if metodo_pagamento == "cartao" else "PIX",
                due_date=dt_local.date().isoformat(),
                descricao=(
                    f"Jogo avulso Roma Tênis — {dt_local.strftime('%d/%m/%Y')} "
                    f"{dt_local.hour:02d}h"
                ),
            )
            asaas_payment_id = charge.get("id")

            self.db.add(Payment(
                booking_id=booking.id,
                valor=valor,
                metodo=MetodoPagamento.CARTAO if metodo_pagamento == "cartao" else MetodoPagamento.PIX,
                status=StatusPagamento.PENDENTE,
                gateway_id=asaas_payment_id,
            ))

            if metodo_pagamento == "cartao":
                return {
                    "invoice_url": charge.get("invoiceUrl"),
                    "msg": "Pré-reserva criada! Pague com cartão no link abaixo — "
                           "o horário é confirmado após a aprovação.",
                }

            qr = await asaas.get_pix_qrcode(asaas_payment_id) if asaas_payment_id else {}
            return {
                "pix_copia_cola": qr.get("payload"),
                "pix_qrcode": qr.get("encodedImage"),
                "msg": "Pré-reserva criada! Pague o PIX abaixo — o horário é "
                       "confirmado assim que o pagamento for identificado.",
            }
        except Exception as e:
            await self.db.rollback()
            raise BookingError(
                "Não foi possível gerar a cobrança do jogo avulso. Tente novamente."
            ) from e

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

    async def _validar_jogo_avulso(
        self,
        player: Player,
        data_hora: datetime,
        tipo: TipoPartida,
        membros_a: list[int],
        membros_b: list[int],
        convidados: list[ConvidadoIn],
    ) -> None:
        agora = datetime.now(timezone.utc)
        if data_hora <= agora:
            raise BookingError("Não é possível reservar no passado")

        antecedencia = data_hora - agora
        if antecedencia > timedelta(hours=1):
            raise BookingError(
                "Jogo avulso só pode ser reservado na última hora "
                "(menos de 1h antes do início)"
            )

        dt_local = data_hora.astimezone(FUSO_BR)
        h_ini, h_fim = await self._horario_funcionamento(dt_local.date())
        if not (h_ini <= dt_local.hour < h_fim):
            raise BookingError("Horário fora do funcionamento da quadra")

        if not player.contrato_assinado:
            raise BookingError("Assine o Termo de Adesão para reservar quadra")
        if not await self._tem_assinatura_ativa(player.id):
            raise BookingError("Assinatura inativa")

        if player.id not in membros_a:
            raise BookingError("Você deve estar no Lado A da partida")

        membros = membros_a + membros_b
        if len(membros) != len(set(membros)):
            raise BookingError("O mesmo jogador não pode estar em ambos os lados")

        esperado = 1 if tipo == TipoPartida.SIMPLES else 2
        conv_a = [c for c in convidados if c.lado == "A"]
        conv_b = [c for c in convidados if c.lado == "B"]
        if len(membros_a) + len(conv_a) != esperado:
            raise BookingError(f"O Lado A deve ter {esperado} jogador(es)")
        if len(membros_b) + len(conv_b) != esperado:
            raise BookingError(f"O Lado B deve ter {esperado} jogador(es)")

        cpfs = [c.cpf for c in convidados]
        if len(cpfs) != len(set(cpfs)):
            raise BookingError("Há convidados repetidos (mesmo CPF)")

        # Cota semanal: o jogo avulso desconta do saldo de cada membro envolvido
        for pid in membros:
            await self._verificar_limite_ativo(pid, tipo)
            await self._verificar_limite_semanal(pid, tipo, data_hora)

        if await self._slot_ocupado(data_hora):
            raise BookingError("Horário já reservado")

    async def _horario_funcionamento(self, data: date) -> tuple[int, int]:
        """Faixa de horas de funcionamento do dia, considerando horário especial."""
        horario_esp = await self._get_horario_especial(data)
        if horario_esp and horario_esp.fechado:
            raise BookingError("Quadra fechada neste dia")
        h_ini = horario_esp.hora_abertura if horario_esp and horario_esp.hora_abertura is not None else 6
        h_fim = horario_esp.hora_fechamento if horario_esp and horario_esp.hora_fechamento is not None else 22
        return h_ini, h_fim

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

    @staticmethod
    def _semana_do_slot(data_hora: datetime) -> tuple[datetime, datetime, date, date]:
        """Semana (seg–dom) que contém o slot, em UTC para query e local para exibição."""
        dt_local = data_hora.astimezone(FUSO_BR)
        inicio_local = (dt_local - timedelta(days=dt_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fim_local = inicio_local + timedelta(days=7)
        return (
            inicio_local.astimezone(timezone.utc),
            fim_local.astimezone(timezone.utc),
            inicio_local.date(),
            (fim_local - timedelta(days=1)).date(),
        )

    async def _contar_jogos_semana(
        self, player_id: int, tipo: TipoPartida, data_hora: datetime
    ) -> int:
        """Partidas confirmadas do tipo na semana do slot — inclui jogos avulsos."""
        inicio_utc, fim_utc, _, _ = self._semana_do_slot(data_hora)
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
        return result.scalar() or 0

    async def uso_semanal(self, player: Player, referencia: datetime | None = None) -> dict:
        """Cota de jogos consumida e restante na semana corrente (seg–dom)."""
        ref = referencia or datetime.now(timezone.utc)
        _, _, semana_inicio, semana_fim = self._semana_do_slot(ref)

        uso = {}
        for tipo in (TipoPartida.SIMPLES, TipoPartida.DUPLAS):
            usados = await self._contar_jogos_semana(player.id, tipo, ref)
            limite = LIMITE_SEMANAL[tipo]
            uso[tipo.value] = {
                "usados": usados,
                "limite": limite,
                "restantes": max(limite - usados, 0),
            }

        return {
            "semana_inicio": semana_inicio,
            "semana_fim": semana_fim,
            "simples": uso["simples"],
            "duplas": uso["duplas"],
        }

    async def _verificar_limite_semanal(
        self, player_id: int, tipo: TipoPartida, data_hora: datetime
    ) -> None:
        count = await self._contar_jogos_semana(player_id, tipo, data_hora)
        limite = LIMITE_SEMANAL[tipo]
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
        jogadores = []
        for p in m.participantes:
            if p.player:
                jogadores.append(JogadorSlot(
                    nome=p.player.nome, apelido=p.player.apelido, lado=p.lado.value,
                ))
            elif p.convidado:
                jogadores.append(JogadorSlot(
                    nome=p.convidado.nome, apelido=p.convidado.apelido, lado=p.lado.value,
                ))
        return {
            "jogadores": jogadores,
            "placar": m.placar,
            "lado_vencedor": m.lado_vencedor,
            "status_partida": m.status.value,
        }

    @staticmethod
    def _filtro_slot_tomado():
        """Reserva confirmada OU pré-reserva recente ainda aguardando pagamento."""
        cutoff = datetime.now(timezone.utc) - JANELA_PRE_RESERVA
        return or_(
            Booking.status == StatusReserva.CONFIRMADA,
            and_(
                Booking.status == StatusReserva.AGUARDANDO_PAGAMENTO,
                Booking.criado_em >= cutoff,
            ),
        )

    async def _slot_ocupado(self, dt_inicio: datetime) -> bool:
        dt_fim = dt_inicio + timedelta(hours=1)
        result = await self.db.execute(
            select(Booking.id).where(
                self._filtro_slot_tomado(),
                Booking.data_hora_inicio < dt_fim,
                Booking.data_hora_fim > dt_inicio,
            )
        )
        return result.first() is not None

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
