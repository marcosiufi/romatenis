"""
Ciclo de vida de assinaturas e integração Asaas.

Fluxo de criação:
  1. Valida método de pagamento (non-mensal → só cartão; PIX só no mensal).
  2. Busca/cria cliente Asaas.
  3. Cria cobrança Asaas.
  4. Auto-envia contrato via Autentique (se ainda não assinado).
  5. Define status do jogador: ASSINATURA ou PAGAMENTO.

Fluxo de confirmação (webhook Asaas → POST /subscriptions/webhook):
  - PAYMENT_RECEIVED / PAYMENT_CONFIRMED → Payment PAGO → player ATIVO (se contrato ok).
  - PAYMENT_OVERDUE → Payment FALHOU, Subscription INADIMPLENTE.
  - PAYMENT_REFUNDED → Payment ESTORNADO, Subscription CANCELADA.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSession
from app.models.booking import Booking, StatusReserva
from app.models.lista_espera import ListaEspera, StatusListaEspera
from app.models.payment import MetodoPagamento, Payment, StatusPagamento
from app.models.configuracao import Configuracao
from app.models.player import NivelJogador, Player, StatusJogador
from app.models.subscription import (
    FormaPagamento,
    PlanoAssinatura,
    StatusAssinatura,
    Subscription,
)
from app.services.asaas_client import BILLING_TYPE_MAP, AsaasClient, AsaasError
from app.services import email_service

FUSO_BR = ZoneInfo("America/Sao_Paulo")

PLANO_MESES: dict[PlanoAssinatura, int] = {
    PlanoAssinatura.MENSAL: 1,
    PlanoAssinatura.TRIMESTRAL: 3,
    PlanoAssinatura.SEMESTRAL: 6,
    PlanoAssinatura.ANUAL: 12,
}

# Número padrão de parcelas por plano para BOLETO e cartão
PLANO_PARCELAS: dict[PlanoAssinatura, int] = {
    PlanoAssinatura.MENSAL: 1,
    PlanoAssinatura.TRIMESTRAL: 3,
    PlanoAssinatura.SEMESTRAL: 6,
    PlanoAssinatura.ANUAL: 12,
}

METODO_MAP: dict[FormaPagamento, MetodoPagamento] = {
    FormaPagamento.PIX_AVISTA: MetodoPagamento.PIX,
    FormaPagamento.BOLETO_AVISTA: MetodoPagamento.BOLETO,
    FormaPagamento.CARTAO_PARCELADO: MetodoPagamento.CARTAO,
}


class SubscriptionError(ValueError):
    pass


class RankingCheioError(Exception):
    def __init__(self, limite: int) -> None:
        self.limite = limite
        super().__init__("ranking_cheio")


class ContratacaoDesabilitadaError(SubscriptionError):
    """Contratações desligadas no painel — usa a mensagem configurada pelo admin."""


@dataclass
class AssinaturaResult:
    subscription: Subscription
    payment: Payment
    payment_link: str | None = field(default=None)
    pix_qrcode_base64: str | None = field(default=None)
    pix_copia_e_cola: str | None = field(default=None)
    contrato_link: str | None = field(default=None)


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._asaas = AsaasClient()

    # ── Criação ───────────────────────────────────────────────────────────────

    async def criar_assinatura(
        self,
        player_id: int,
        plano: PlanoAssinatura,
        forma_pagamento: FormaPagamento,
        valor_mensal: float,
        parcelas: int = 1,
    ) -> AssinaturaResult:
        player = await self.db.get(Player, player_id)
        if not player:
            raise SubscriptionError("Jogador não encontrado")

        # Validação de método de pagamento
        if forma_pagamento == FormaPagamento.BOLETO_AVISTA:
            raise SubscriptionError("Boleto não está disponível. Use PIX (5% de desconto, à vista) ou Cartão de Crédito.")

        if await self._get_ativa(player_id):
            raise SubscriptionError("Jogador já possui assinatura ativa")

        meses = PLANO_MESES[plano]
        valor_total = round(valor_mensal * meses, 2)
        # PIX: 5% de desconto, sempre à vista
        if forma_pagamento == FormaPagamento.PIX_AVISTA:
            valor_total = round(valor_total * 0.95, 2)
        now_br = datetime.now(FUSO_BR)
        expiracao = now_br + timedelta(days=meses * 30)

        # Garante que o jogador existe no Asaas e tem CPF (exigido para PIX)
        nasc = player.data_nascimento.isoformat() if player.data_nascimento else None
        customer_id = await self._asaas.get_or_create_customer(
            player.nome, player.email, player.telefone,
            cpf=player.cpf, data_nascimento=nasc,
        )
        player.asaas_customer_id = customer_id

        billing_type = BILLING_TYPE_MAP[forma_pagamento.value]
        due_date = (now_br + timedelta(days=3)).strftime("%Y-%m-%d")
        descricao = f"Assinatura {plano.value} — Ranking de Tênis"

        # PIX não suporta parcelamento no Asaas; boleto e cartão suportam
        installment_count = (
            parcelas
            if forma_pagamento in (FormaPagamento.BOLETO_AVISTA, FormaPagamento.CARTAO_PARCELADO)
            else 1
        )

        try:
            cobranca = await self._asaas.criar_cobranca(
                customer_id=player.asaas_customer_id,
                valor=valor_total,
                billing_type=billing_type,
                due_date=due_date,
                descricao=descricao,
                installment_count=installment_count,
            )
        except AsaasError as e:
            raise SubscriptionError(str(e))

        sub = Subscription(
            player_id=player_id,
            plano=plano,
            valor_mensal=valor_mensal,
            valor_total_ciclo=valor_total,
            forma_pagamento=forma_pagamento,
            parcelas=parcelas,
            status=StatusAssinatura.PENDENTE,
            data_inicio_ciclo=now_br,
            data_expiracao=expiracao,
            gateway_subscription_id=cobranca["id"],
            aviso_7d_enviado=False,
            aviso_1d_enviado=False,
        )
        self.db.add(sub)
        await self.db.flush()

        payment = Payment(
            subscription_id=sub.id,
            valor=valor_total,
            metodo=METODO_MAP[forma_pagamento],
            status=StatusPagamento.PENDENTE,
            gateway_id=cobranca["id"],
        )
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(sub)

        result = AssinaturaResult(
            subscription=sub,
            payment=payment,
            payment_link=cobranca.get("invoiceUrl") or cobranca.get("bankSlipUrl"),
        )

        if billing_type == "PIX":
            try:
                qr = await self._asaas.get_pix_qrcode(cobranca["id"])
                result.pix_qrcode_base64 = qr.get("encodedImage")
                result.pix_copia_e_cola = qr.get("payload")
            except Exception:
                pass

        # Auto-envio de contrato e atualização de status
        now_utc = datetime.now(timezone.utc)
        if not player.contrato_assinado:
            from app.services.autentique_client import AutentiqueClient, AutentiqueError
            from app.models.contrato import ContratoClausula
            from app.models.configuracao import Configuracao
            client = AutentiqueClient()
            # Carrega cláusulas editáveis do banco
            _res = await self.db.execute(
                select(ContratoClausula)
                .where(ContratoClausula.ativo == True)
                .order_by(ContratoClausula.ordem)
            )
            _clausulas = [
                {"titulo": c.titulo, "texto": c.texto}
                for c in _res.scalars()
            ]
            # Carrega dados da empresa para o cabeçalho do PDF
            _cfg = await Configuracao.get(self.db)
            _empresa = {
                "razao_social":    _cfg.razao_social,
                "cpf_responsavel": _cfg.cpf_responsavel,
                "cnpj":            _cfg.cnpj,
                "nome_fantasia":   _cfg.nome_fantasia,
            }
            try:
                doc_id, link = await client.enviar_contrato(
                    nome=player.nome,
                    email=player.email,
                    cpf=player.cpf,
                    telefone=player.telefone,
                    clausulas=_clausulas or None,
                    empresa=_empresa,
                )
                player.contrato_autentique_id = doc_id
                player.contrato_link_assinatura = link
                player.contrato_enviado_em = now_utc
                player.contrato_assinado = False
                result.contrato_link = link
            except AutentiqueError as e:
                logger.error("Erro ao enviar contrato automático: %s", e)
            player.status = StatusJogador.ASSINATURA.value
        else:
            result.contrato_link = player.contrato_link_assinatura
            player.status = StatusJogador.PAGAMENTO.value

        await self.db.commit()
        return result

    async def contratar(self, player: Player, plano: PlanoAssinatura, forma_pagamento: FormaPagamento) -> "AssinaturaResult":
        """Primeira contratação pelo próprio jogador a partir da landing page."""
        if await self._get_ativa(player.id):
            raise SubscriptionError("Você já possui uma assinatura ativa.")

        config = await Configuracao.get(self.db)
        if not config.contratacao_planos_ativa:
            raise ContratacaoDesabilitadaError(config.msg_planos_desabilitado)
        if await self._ranking_cheio(config.limite_ranking):
            raise RankingCheioError(config.limite_ranking)
        meses = PLANO_MESES[plano]
        precos_totais = {
            PlanoAssinatura.MENSAL:     float(config.preco_mensal),
            PlanoAssinatura.TRIMESTRAL: float(config.preco_trimestral),
            PlanoAssinatura.SEMESTRAL:  float(config.preco_semestral),
            PlanoAssinatura.ANUAL:      float(config.preco_anual),
        }
        valor_mensal_unitario = round(precos_totais[plano] / meses, 2)
        parcelas = PLANO_PARCELAS[plano]
        return await self.criar_assinatura(player.id, plano, forma_pagamento, valor_mensal_unitario, parcelas)

    async def renovar(self, player: Player, plano: PlanoAssinatura, forma_pagamento: FormaPagamento) -> "AssinaturaResult":
        """Jogador renova sua própria assinatura (expirada ou expirando em ≤7 dias)."""
        from app.core.config import settings as cfg

        sub_ativa = await self._get_ativa(player.id)
        if sub_ativa:
            dias_restantes = (sub_ativa.data_expiracao - datetime.now(timezone.utc)).days
            if dias_restantes > 7:
                raise SubscriptionError("Você ainda tem mais de 7 dias de assinatura ativa.")

        config = await Configuracao.get(self.db)
        if not config.contratacao_planos_ativa:
            raise ContratacaoDesabilitadaError(config.msg_planos_desabilitado)
        meses = PLANO_MESES[plano]
        precos_totais = {
            PlanoAssinatura.MENSAL:      float(config.preco_mensal),
            PlanoAssinatura.TRIMESTRAL:  float(config.preco_trimestral),
            PlanoAssinatura.SEMESTRAL:   float(config.preco_semestral),
            PlanoAssinatura.ANUAL:       float(config.preco_anual),
        }
        valor_total_plano = precos_totais[plano]
        valor_mensal_unitario = round(valor_total_plano / meses, 2)
        parcelas = PLANO_PARCELAS[plano]
        return await self.criar_assinatura(player.id, plano, forma_pagamento, valor_mensal_unitario, parcelas)

    async def admin_atualizar_status(
        self,
        sub_id: int,
        novo_status: "StatusAssinatura",
        data_pausa: "datetime | None" = None,
        data_retorno_prevista: "datetime | None" = None,
        notas: "str | None" = None,
    ) -> "Subscription":
        sub = await self.db.get(Subscription, sub_id, options=[selectinload(Subscription.player)])
        if not sub:
            raise SubscriptionError("Assinatura não encontrada")

        status_anterior = sub.status
        sub.status = novo_status
        if notas is not None:
            sub.notas = notas

        if novo_status == StatusAssinatura.PAUSADA:
            pausa_inicio = data_pausa or datetime.now(FUSO_BR)
            if data_retorno_prevista:
                retorno_naive = data_retorno_prevista.replace(tzinfo=None)
                pausa_naive = pausa_inicio.replace(tzinfo=None)
                if (retorno_naive - pausa_naive).days > 15:
                    raise SubscriptionError("A pausa máxima permitida é de 15 dias.")
            sub.data_pausa = pausa_inicio
            sub.data_retorno_prevista = data_retorno_prevista
            sub.pausa_solicitada = False
            if sub.player:
                sub.player.status = StatusJogador.INATIVO.value
            await self.db.commit()
            await self.db.refresh(sub)
            data_ret_str = sub.data_retorno_prevista.strftime("%d/%m/%Y") if sub.data_retorno_prevista else None
            await email_service.enviar_aviso_pausa(sub.player.nome, sub.player.email, data_ret_str)
        else:
            if status_anterior == StatusAssinatura.PAUSADA and novo_status == StatusAssinatura.ATIVA:
                if sub.player:
                    sub.player.status = StatusJogador.ATIVO.value
            sub.pausa_solicitada = False
            await self.db.commit()
            await self.db.refresh(sub)

        return sub

    async def solicitar_pausa(self, player: Player, motivo: str, data_inicio: date, dias_pausa: int) -> None:
        """Registra o pedido de pausa — admin será notificado por e-mail."""
        from app.core.config import settings as cfg
        from app.services import email_service as em

        sub = await self._get_ativa(player.id)
        if not sub:
            raise SubscriptionError("Nenhuma assinatura ativa para pausar.")

        if sub.plano == PlanoAssinatura.MENSAL:
            raise SubscriptionError("Pausa não está disponível para o plano mensal.")

        if not motivo or not motivo.strip():
            raise SubscriptionError("O motivo da pausa é obrigatório.")

        data_inicio_dt = datetime(data_inicio.year, data_inicio.month, data_inicio.day, tzinfo=FUSO_BR)
        data_retorno_dt = data_inicio_dt + timedelta(days=dias_pausa)

        sub.pausa_solicitada = True
        sub.pausa_motivo = motivo.strip()
        sub.data_pausa = data_inicio_dt
        sub.data_retorno_prevista = data_retorno_dt
        await self.db.commit()

        corpo = f"""
        <p>O jogador <strong>{player.nome}</strong> ({player.email}) solicitou pausa na assinatura.</p>
        <p><strong>Plano:</strong> {sub.plano.value} &nbsp; <strong>Vence:</strong> {sub.data_expiracao.strftime('%d/%m/%Y')}</p>
        <p><strong>Motivo:</strong> {motivo}</p>
        <p><strong>Período solicitado:</strong> {data_inicio_dt.strftime('%d/%m/%Y')} → {data_retorno_dt.strftime('%d/%m/%Y')} ({dias_pausa} dias)</p>
        <p>Acesse o painel admin para aprovar a pausa.</p>"""

        if cfg.SMTP_USER:
            await em.send_email(
                cfg.SMTP_USER,
                f"⏸ Solicitação de pausa — {player.nome}",
                em._html_base("Solicitação de Pausa", corpo),
            )

    async def get_pix_pendente(self, player: Player) -> "AssinaturaResult | None":
        """Retorna o PIX de pagamento pendente mais recente do jogador."""
        result = await self.db.execute(
            select(Payment)
            .join(Subscription)
            .where(
                Subscription.player_id == player.id,
                Payment.status == StatusPagamento.PENDENTE,
                Payment.gateway_id.is_not(None),
            )
            .order_by(Payment.id.desc())
        )
        payment = result.scalar_one_or_none()
        if not payment or not payment.gateway_id:
            return None

        sub = await self.db.get(Subscription, payment.subscription_id)
        res = AssinaturaResult(subscription=sub, payment=payment)
        try:
            cobranca = await self._asaas.get_cobranca(payment.gateway_id)
            res.payment_link = cobranca.get("invoiceUrl") or cobranca.get("bankSlipUrl")
            billing_type = BILLING_TYPE_MAP.get(sub.forma_pagamento.value, "")
            if billing_type == "PIX":
                qr = await self._asaas.get_pix_qrcode(payment.gateway_id)
                res.pix_qrcode_base64 = qr.get("encodedImage")
                res.pix_copia_e_cola = qr.get("payload")
        except Exception:
            pass
        return res

    # ── Consultas ─────────────────────────────────────────────────────────────

    async def listar_minhas(self, player: Player) -> list[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.player_id == player.id)
            .order_by(Subscription.data_inicio_ciclo.desc())
        )
        return list(result.scalars().all())

    async def listar_todas(self) -> list[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.player))
            .order_by(Subscription.data_inicio_ciclo.desc())
        )
        return list(result.scalars().all())

    async def minha_ativa(self, player: Player) -> Subscription | None:
        """Retorna ATIVA (preferência) ou PENDENTE — para o perfil do jogador."""
        ativa = await self._get_ativa(player.id)
        if ativa:
            return ativa
        result = await self.db.execute(
            select(Subscription)
            .where(
                Subscription.player_id == player.id,
                Subscription.status == StatusAssinatura.PENDENTE,
            )
            .order_by(Subscription.data_inicio_ciclo.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Ações ─────────────────────────────────────────────────────────────────

    async def solicitar_antecipacao(self, subscription_id: int) -> Subscription:
        sub = await self.db.get(Subscription, subscription_id)
        if not sub:
            raise SubscriptionError("Assinatura não encontrada")
        if sub.forma_pagamento != FormaPagamento.CARTAO_PARCELADO:
            raise SubscriptionError("Antecipação disponível apenas para cartão parcelado")
        if sub.antecipacao_solicitada:
            raise SubscriptionError("Antecipação já solicitada para esta assinatura")

        result = await self.db.execute(
            select(Payment).where(
                Payment.subscription_id == subscription_id,
                Payment.status == StatusPagamento.PENDENTE,
            )
        )
        payment = result.scalar_one_or_none()
        if not payment or not payment.gateway_id:
            raise SubscriptionError("Nenhum pagamento pendente encontrado para antecipar")

        try:
            await self._asaas.solicitar_antecipacao(payment.gateway_id)
        except AsaasError as e:
            raise SubscriptionError(str(e))

        sub.antecipacao_solicitada = True
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def processar_webhook(self, event: str, payment_data: dict) -> None:
        gateway_id = payment_data.get("id")
        if not gateway_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.gateway_id == gateway_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return

        asaas_status = payment_data.get("status", "")

        if event in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED") or asaas_status in ("RECEIVED", "CONFIRMED"):
            payment.status = StatusPagamento.PAGO
            payment.data_pagamento = datetime.now(timezone.utc)
            if payment.booking_id:
                booking = await self.db.get(Booking, payment.booking_id)
                if booking and booking.status == StatusReserva.AGUARDANDO_PAGAMENTO:
                    booking.status = StatusReserva.CONFIRMADA
            if payment.subscription_id:
                sub = await self.db.get(Subscription, payment.subscription_id, options=[selectinload(Subscription.player)])
                if sub and sub.player:
                    if sub.player.contrato_assinado:
                        sub.status = StatusAssinatura.ATIVA
                        sub.player.status = StatusJogador.ATIVO.value
                    else:
                        # Pagamento confirmado mas contrato ainda não assinado
                        sub.player.status = StatusJogador.PAGAMENTO.value
                    data_str = sub.data_expiracao.astimezone(FUSO_BR).strftime("%d/%m/%Y")
                    await email_service.enviar_confirmacao_pagamento(
                        sub.player.nome, sub.player.email, sub.plano.value, data_str
                    )

        elif asaas_status == "OVERDUE":
            payment.status = StatusPagamento.FALHOU
            if payment.subscription_id:
                sub = await self.db.get(Subscription, payment.subscription_id)
                if sub:
                    sub.status = StatusAssinatura.INADIMPLENTE

        elif asaas_status in ("REFUNDED", "REFUND_REQUESTED") or event == "PAYMENT_REFUNDED":
            payment.status = StatusPagamento.ESTORNADO
            if payment.subscription_id:
                sub = await self.db.get(Subscription, payment.subscription_id)
                if sub:
                    sub.status = StatusAssinatura.CANCELADA
                    await self.db.commit()
                    await self.notificar_proximo_na_fila()
                    return

        await self.db.commit()

    async def verificar_expiracoes(self) -> int:
        """Marca assinaturas vencidas como EXPIRADA e coloca jogador em RENOVACAO (7 dias para renovar)."""
        agora = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.player))
            .where(
                Subscription.status == StatusAssinatura.ATIVA,
                Subscription.data_expiracao <= agora,
            )
        )
        subs = list(result.scalars().all())
        for sub in subs:
            sub.status = StatusAssinatura.EXPIRADA
            player = sub.player
            if player and player.status == StatusJogador.ATIVO.value:
                player.status = StatusJogador.RENOVACAO.value
                player.data_inativacao = agora  # início do período de 7 dias
        if subs:
            await self.db.commit()
            await self.notificar_proximo_na_fila()
        return len(subs)

    async def expirar_renovacao(self) -> int:
        """Move para INATIVO jogadores em RENOVACAO há mais de 7 dias."""
        sete_dias_atras = datetime.now(timezone.utc) - timedelta(days=7)
        result = await self.db.execute(
            select(Player).where(
                Player.status == StatusJogador.RENOVACAO.value,
                Player.data_inativacao <= sete_dias_atras,
            )
        )
        players = list(result.scalars().all())
        for p in players:
            p.status = StatusJogador.INATIVO.value
        if players:
            await self.db.commit()
        return len(players)

    async def resetar_nivel_inativos(self) -> int:
        """Zera nivel de jogadores inativos há mais de 90 dias."""
        noventa_dias_atras = datetime.now(timezone.utc) - timedelta(days=90)
        result = await self.db.execute(
            select(Player).where(
                Player.status == StatusJogador.INATIVO.value,
                Player.data_inativacao <= noventa_dias_atras,
                Player.nivel != NivelJogador.NAO_CLASSIFICADO.value,
            )
        )
        players = list(result.scalars().all())
        for p in players:
            p.nivel = NivelJogador.NAO_CLASSIFICADO
            p.rating_atual = 1000.0
        if players:
            await self.db.commit()
        return len(players)

    async def enviar_avisos_vencimento(self) -> int:
        """Envia e-mails de aviso para assinaturas que vencem em 7 ou 1 dia."""
        from app.core.config import settings as cfg

        agora = datetime.now(timezone.utc)
        enviados = 0

        for dias, campo in [(7, "aviso_7d_enviado"), (1, "aviso_1d_enviado")]:
            limite_inf = agora + timedelta(days=dias - 1)
            limite_sup = agora + timedelta(days=dias)
            result = await self.db.execute(
                select(Subscription)
                .options(selectinload(Subscription.player))
                .where(
                    Subscription.status == StatusAssinatura.ATIVA,
                    Subscription.data_expiracao >= limite_inf,
                    Subscription.data_expiracao < limite_sup,
                    getattr(Subscription, campo) == False,
                )
            )
            for sub in result.scalars().all():
                data_str = sub.data_expiracao.astimezone(FUSO_BR).strftime("%d/%m/%Y")
                link = f"{cfg.DOMAIN}/"
                await email_service.enviar_aviso_vencimento(
                    sub.player.nome, sub.player.email, sub.plano.value, dias, data_str, link
                )
                setattr(sub, campo, True)
                enviados += 1

        if enviados:
            await self.db.commit()
        return enviados

    # ── Lista de Espera ───────────────────────────────────────────────────────

    async def entrar_na_lista_espera(self, player: Player) -> ListaEspera:
        from app.core.config import settings as cfg

        # Verifica se já está na fila (aguardando ou convocado)
        existente = await self.db.execute(
            select(ListaEspera).where(
                ListaEspera.player_id == player.id,
                ListaEspera.status.in_([StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO]),
            )
        )
        if existente.scalar_one_or_none():
            raise SubscriptionError("Você já está na lista de espera.")

        if await self._get_ativa(player.id):
            raise SubscriptionError("Você já possui uma assinatura ativa.")

        agora = datetime.now(timezone.utc)
        entrada = ListaEspera(
            player_id=player.id,
            status=StatusListaEspera.AGUARDANDO,
            data_inscricao=agora,
        )
        self.db.add(entrada)
        await self.db.commit()
        await self.db.refresh(entrada)

        posicao = await self._posicao_na_fila(entrada.id)
        try:
            await email_service.enviar_confirmacao_lista_espera(player.nome, player.email, posicao)
        except Exception:
            pass

        return entrada

    async def sair_da_lista_espera(self, player: Player) -> None:
        result = await self.db.execute(
            select(ListaEspera).where(
                ListaEspera.player_id == player.id,
                ListaEspera.status.in_([StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO]),
            )
        )
        entrada = result.scalar_one_or_none()
        if not entrada:
            raise SubscriptionError("Você não está na lista de espera.")
        entrada.status = StatusListaEspera.REMOVIDO
        await self.db.commit()

    async def minha_posicao_lista(self, player: Player) -> dict | None:
        result = await self.db.execute(
            select(ListaEspera).where(
                ListaEspera.player_id == player.id,
                ListaEspera.status.in_([StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO]),
            )
        )
        entrada = result.scalar_one_or_none()
        if not entrada:
            return None
        posicao = await self._posicao_na_fila(entrada.id)
        return {
            "id": entrada.id,
            "status": entrada.status.value,
            "posicao": posicao,
            "data_inscricao": entrada.data_inscricao.isoformat(),
            "data_expiracao_convocacao": entrada.data_expiracao_convocacao.isoformat() if entrada.data_expiracao_convocacao else None,
        }

    async def listar_fila_espera(self) -> list[dict]:
        result = await self.db.execute(
            select(ListaEspera)
            .where(ListaEspera.status.in_([StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO]))
            .order_by(ListaEspera.data_inscricao.asc())
        )
        entradas = list(result.scalars().all())
        items = []
        for pos, entrada in enumerate(entradas, 1):
            player = await self.db.get(Player, entrada.player_id)
            items.append({
                "id": entrada.id,
                "posicao": pos,
                "status": entrada.status.value,
                "data_inscricao": entrada.data_inscricao.isoformat(),
                "data_expiracao_convocacao": entrada.data_expiracao_convocacao.isoformat() if entrada.data_expiracao_convocacao else None,
                "player_id": entrada.player_id,
                "player_nome": player.nome if player else "—",
                "player_email": player.email if player else "—",
                "player_telefone": player.telefone if player else "—",
            })
        return items

    async def admin_remover_da_fila(self, entrada_id: int) -> None:
        entrada = await self.db.get(ListaEspera, entrada_id)
        if not entrada:
            raise SubscriptionError("Entrada não encontrada.")
        entrada.status = StatusListaEspera.REMOVIDO
        await self.db.commit()
        # Após remover, notifica o próximo
        await self.notificar_proximo_na_fila()

    async def admin_convocar_da_fila(self, entrada_id: int) -> None:
        entrada = await self.db.get(ListaEspera, entrada_id, options=[])
        if not entrada or entrada.status not in (StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO):
            raise SubscriptionError("Entrada não encontrada ou já processada.")
        await self._convocar_entrada(entrada)
        await self.db.commit()

    async def notificar_proximo_na_fila(self) -> None:
        """Convoca o primeiro AGUARDANDO da lista quando uma vaga abre."""
        result = await self.db.execute(
            select(ListaEspera)
            .where(ListaEspera.status == StatusListaEspera.AGUARDANDO)
            .order_by(ListaEspera.data_inscricao.asc())
            .limit(1)
        )
        proximo = result.scalar_one_or_none()
        if proximo:
            await self._convocar_entrada(proximo)
            await self.db.commit()

    async def verificar_convocacoes_expiradas(self) -> int:
        """Expira convocações não atendidas em 48h e convoca o próximo."""
        agora = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(ListaEspera).where(
                ListaEspera.status == StatusListaEspera.CONVOCADO,
                ListaEspera.data_expiracao_convocacao <= agora,
            )
        )
        expirados = list(result.scalars().all())
        for entrada in expirados:
            entrada.status = StatusListaEspera.EXPIRADO
        if expirados:
            await self.db.commit()
            await self.notificar_proximo_na_fila()
        return len(expirados)

    async def vagas_ranking(self) -> dict:
        config = await Configuracao.get(self.db)
        ocupadas = await self._contar_ativos()
        return {
            "limite": config.limite_ranking,
            "ocupadas": ocupadas,
            "disponiveis": max(0, config.limite_ranking - ocupadas),
            "cheio": ocupadas >= config.limite_ranking,
        }

    async def _convocar_entrada(self, entrada: ListaEspera) -> None:
        from app.core.config import settings as cfg
        agora = datetime.now(timezone.utc)
        entrada.status = StatusListaEspera.CONVOCADO
        entrada.data_convocacao = agora
        entrada.data_expiracao_convocacao = agora + timedelta(hours=48)
        player = await self.db.get(Player, entrada.player_id)
        if player:
            link = f"{cfg.DOMAIN}/"
            try:
                await email_service.enviar_convocacao_lista_espera(player.nome, player.email, 48, link)
            except Exception:
                pass

    async def _posicao_na_fila(self, entrada_id: int) -> int:
        result = await self.db.execute(
            select(ListaEspera)
            .where(
                ListaEspera.status.in_([StatusListaEspera.AGUARDANDO, StatusListaEspera.CONVOCADO]),
                ListaEspera.id <= entrada_id,
            )
            .order_by(ListaEspera.data_inscricao.asc())
        )
        return len(list(result.scalars().all()))

    async def _ranking_cheio(self, limite: int) -> bool:
        ocupadas = await self._contar_ativos()
        return ocupadas >= limite

    async def _contar_ativos(self) -> int:
        return (
            await self.db.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.status == StatusAssinatura.ATIVA,
                    Subscription.data_expiracao > datetime.now(timezone.utc),
                )
            )
        ) or 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_ativa(self, player_id: int) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.player_id == player_id,
                Subscription.status == StatusAssinatura.ATIVA,
                Subscription.data_expiracao > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()
