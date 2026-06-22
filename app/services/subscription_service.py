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
from app.models.player import Player
from app.models.subscription import (
    FormaPagamento,
    PlanoAssinatura,
    StatusAssinatura,
    Subscription,
)
from app.services.asaas_client import BILLING_TYPE_MAP, AsaasClient, AsaasError

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
            customer_id = await self._asaas.get_or_create_customer(
                player.nome, player.email, player.telefone
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
        """Marca assinaturas ATIVA com data_expiracao vencida como EXPIRADA."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.status == StatusAssinatura.ATIVA,
                Subscription.data_expiracao <= datetime.now(timezone.utc),
            )
        )
        subs = list(result.scalars().all())
        for sub in subs:
            sub.status = StatusAssinatura.EXPIRADA
        if subs:
            await self.db.commit()
        return len(subs)

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
