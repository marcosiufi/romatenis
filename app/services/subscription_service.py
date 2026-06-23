"""
Ciclo de vida de assinaturas e integração Asaas.

Fluxo de criação (feito pelo admin):
  1. Busca/cria cliente Asaas com dados do jogador.
  2. Cria cobrança Asaas (PIX / boleto / cartão parcelado).
  3. Salva Subscription + Payment no banco com status otimista ATIVA/PENDENTE.
  4. Retorna AssinaturaResult com link de pagamento e QR Pix.

Fluxo de confirmação (webhook Asaas → POST /subscriptions/webhook):
  - PAYMENT_RECEIVED / PAYMENT_CONFIRMED → Payment PAGO.
  - PAYMENT_OVERDUE → Payment FALHOU, Subscription INADIMPLENTE.
  - PAYMENT_REFUNDED → Payment ESTORNADO, Subscription CANCELADA.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSession
from app.models.payment import MetodoPagamento, Payment, StatusPagamento
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

METODO_MAP: dict[FormaPagamento, MetodoPagamento] = {
    FormaPagamento.PIX_AVISTA: MetodoPagamento.PIX,
    FormaPagamento.BOLETO_AVISTA: MetodoPagamento.BOLETO,
    FormaPagamento.CARTAO_PARCELADO: MetodoPagamento.CARTAO,
}


class SubscriptionError(ValueError):
    pass


@dataclass
class AssinaturaResult:
    subscription: Subscription
    payment: Payment
    payment_link: str | None = field(default=None)
    pix_qrcode_base64: str | None = field(default=None)
    pix_copia_e_cola: str | None = field(default=None)


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

        if await self._get_ativa(player_id):
            raise SubscriptionError("Jogador já possui assinatura ativa")

        meses = PLANO_MESES[plano]
        valor_total = round(valor_mensal * meses, 2)
        now_br = datetime.now(FUSO_BR)
        expiracao = now_br + timedelta(days=meses * 30)

        # Garante que o jogador existe no Asaas
        if not player.asaas_customer_id:
            nasc = player.data_nascimento.isoformat() if player.data_nascimento else None
            customer_id = await self._asaas.get_or_create_customer(
                player.nome, player.email, player.telefone,
                cpf=player.cpf, data_nascimento=nasc,
            )
            player.asaas_customer_id = customer_id

        billing_type = BILLING_TYPE_MAP[forma_pagamento.value]
        due_date = (now_br + timedelta(days=3)).strftime("%Y-%m-%d")
        descricao = f"Assinatura {plano.value} — Ranking de Tênis"

        try:
            cobranca = await self._asaas.criar_cobranca(
                customer_id=player.asaas_customer_id,
                valor=valor_total,
                billing_type=billing_type,
                due_date=due_date,
                descricao=descricao,
                installment_count=parcelas if forma_pagamento == FormaPagamento.CARTAO_PARCELADO else 1,
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
            status=StatusAssinatura.ATIVA,
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

        return result

    async def renovar(self, player: Player, plano: PlanoAssinatura, forma_pagamento: FormaPagamento) -> "AssinaturaResult":
        """Jogador renova sua própria assinatura (expirada ou expirando em ≤7 dias)."""
        from app.core.config import settings as cfg

        sub_ativa = await self._get_ativa(player.id)
        if sub_ativa:
            dias_restantes = (sub_ativa.data_expiracao - datetime.now(timezone.utc)).days
            if dias_restantes > 7:
                raise SubscriptionError("Você ainda tem mais de 7 dias de assinatura ativa.")

        precos = {
            PlanoAssinatura.MENSAL: cfg.PRECO_MENSAL,
            PlanoAssinatura.TRIMESTRAL: cfg.PRECO_TRIMESTRAL,
            PlanoAssinatura.SEMESTRAL: cfg.PRECO_SEMESTRAL,
            PlanoAssinatura.ANUAL: cfg.PRECO_ANUAL,
        }
        valor_mensal = precos[plano]
        return await self.criar_assinatura(player.id, plano, forma_pagamento, valor_mensal)

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

        sub.status = novo_status
        if notas is not None:
            sub.notas = notas

        if novo_status == StatusAssinatura.PAUSADA:
            sub.data_pausa = data_pausa or datetime.now(FUSO_BR)
            sub.data_retorno_prevista = data_retorno_prevista
            await self.db.commit()
            await self.db.refresh(sub)
            data_ret_str = sub.data_retorno_prevista.strftime("%d/%m/%Y") if sub.data_retorno_prevista else None
            await email_service.enviar_aviso_pausa(sub.player.nome, sub.player.email, data_ret_str)
        else:
            await self.db.commit()
            await self.db.refresh(sub)

        return sub

    async def solicitar_pausa(self, player: Player, motivo: str | None) -> None:
        """Registra o pedido de pausa — admin será notificado por e-mail."""
        from app.core.config import settings as cfg
        from app.services import email_service as em

        sub = await self._get_ativa(player.id)
        if not sub:
            raise SubscriptionError("Nenhuma assinatura ativa para pausar.")

        corpo = f"""
        <p>O jogador <strong>{player.nome}</strong> ({player.email}) solicitou pausa na assinatura.</p>
        <p><strong>Plano:</strong> {sub.plano.value} &nbsp; <strong>Vence:</strong> {sub.data_expiracao.strftime('%d/%m/%Y')}</p>
        <p><strong>Motivo:</strong> {motivo or '(não informado)'}</p>
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
        return await self._get_ativa(player.id)

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
            if payment.subscription_id:
                sub = await self.db.get(Subscription, payment.subscription_id, options=[selectinload(Subscription.player)])
                if sub and sub.player:
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

    async def verificar_expiracoes(self) -> int:
        """Marca assinaturas ATIVA com data_expiracao vencida como EXPIRADA e inativa o jogador."""
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
                player.status = StatusJogador.INATIVO.value
                player.data_inativacao = agora
        if subs:
            await self.db.commit()
        return len(subs)

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
