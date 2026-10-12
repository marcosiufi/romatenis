"""Visão financeira do clube: o que entrou, o que falta receber e de onde vem.

A fonte é uma só — a tabela de pagamentos. Cada pagamento pertence a uma
assinatura (plano) ou a uma reserva (locação avulsa ou jogo avulso), e é por aí
que se classifica.

**Data de referência.** Pago, um pagamento vale na data em que foi pago. Ainda
não pago, vale na data da origem: o início do ciclo do plano ou o horário da
reserva. É o que decide em que mês ele aparece e se está "em atraso".

**Mês em Brasília.** O banco guarda UTC; o corte do mês é feito no fuso do
clube, senão um PIX das 22h do dia 31 cairia no mês seguinte.

As contas são feitas em Python, não em SQL agregado: um clube tem centenas de
pagamentos por ano, e assim a regra da data de referência e o corte de fuso
ficam num lugar só, legíveis, em vez de repetidos em três consultas.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, TipoReserva
from app.models.payment import Payment, StatusPagamento
from app.models.subscription import Subscription

FUSO = ZoneInfo("America/Sao_Paulo")

ROTULO_PLANO = {
    "mensal": "Plano mensal",
    "trimestral": "Plano trimestral",
    "semestral": "Plano semestral",
    "anual": "Plano anual",
}


@dataclass
class Transacao:
    id: int
    categoria: str          # plano | locacao | avulso | outro
    titulo: str
    pessoa: str
    valor: float
    metodo: str
    status: str             # pendente | pago | falhou | estornado
    data: datetime          # data de referência (ver docstring do módulo)
    pago_em: datetime | None
    cupom: str | None
    desconto: float | None
    player_id: int | None

    def como_dict(self) -> dict:
        return {
            "id": self.id,
            "categoria": self.categoria,
            "titulo": self.titulo,
            "pessoa": self.pessoa,
            "valor": round(self.valor, 2),
            "metodo": self.metodo,
            "status": self.status,
            "data": self.data.isoformat(),
            "pago_em": self.pago_em.isoformat() if self.pago_em else None,
            "cupom": self.cupom,
            "desconto": round(self.desconto, 2) if self.desconto else None,
            "player_id": self.player_id,
        }


def _limites_mes(ano: int, mes: int) -> tuple[datetime, datetime]:
    """Início e fim (exclusivo) do mês no fuso do clube, em UTC."""
    inicio = datetime(ano, mes, 1, tzinfo=FUSO)
    fim = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=FUSO)
    return inicio.astimezone(timezone.utc), fim.astimezone(timezone.utc)


def _mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def _para_transacao(p: Payment) -> Transacao:
    sub, bk = p.subscription, p.booking
    if sub is not None:
        categoria = "plano"
        titulo = ROTULO_PLANO.get(sub.plano.value, "Plano")
        pessoa = sub.player.nome if sub.player else ""
        origem = sub.data_inicio_ciclo
        player_id = sub.player_id
    elif bk is not None:
        if bk.tipo == TipoReserva.LOCACAO_AVULSA:
            categoria, titulo = "locacao", "Locação da quadra"
            pessoa = bk.cliente_locacao_nome or (bk.jogador_responsavel.nome if bk.jogador_responsavel else "")
        elif bk.tipo == TipoReserva.JOGO_AVULSO:
            categoria, titulo = "avulso", "Jogo avulso"
            pessoa = bk.jogador_responsavel.nome if bk.jogador_responsavel else ""
        else:
            categoria, titulo = "outro", "Reserva"
            pessoa = bk.jogador_responsavel.nome if bk.jogador_responsavel else ""
        origem = bk.data_hora_inicio
        player_id = bk.jogador_responsavel_id
    else:
        categoria, titulo, pessoa, origem, player_id = "outro", "Pagamento", "", None, None

    data = p.data_pagamento or origem or datetime.now(timezone.utc)
    return Transacao(
        id=p.id,
        categoria=categoria,
        titulo=titulo,
        pessoa=pessoa,
        valor=float(p.valor),
        metodo=p.metodo.value,
        status=p.status.value,
        data=data,
        pago_em=p.data_pagamento,
        cupom=p.cupom_codigo,
        desconto=float(p.valor_desconto) if p.valor_desconto else None,
        player_id=player_id,
    )


def _consulta_base():
    return select(Payment).options(
        selectinload(Payment.subscription).selectinload(Subscription.player),
        selectinload(Payment.booking).selectinload(Booking.jogador_responsavel),
    )


class FinanceiroService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _todas(self, desde: datetime | None = None) -> list[Transacao]:
        """Pagamentos com data de referência a partir de `desde` + todos os pendentes.

        Os pendentes entram sempre: "a receber" é um saldo, não um recorte do
        mês — uma mensalidade de agosto ainda aberta continua devida em outubro.
        """
        consulta = _consulta_base()
        if desde is not None:
            consulta = consulta.where(or_(
                Payment.status == StatusPagamento.PENDENTE,
                Payment.data_pagamento >= desde,
                Payment.data_pagamento.is_(None),
            ))
        linhas = (await self.db.execute(consulta)).scalars().all()
        return [_para_transacao(p) for p in linhas]

    async def resumo(self, ano: int, mes: int) -> dict:
        agora = datetime.now(timezone.utc)
        ini, fim = _limites_mes(ano, mes)
        ant_ini, ant_fim = _limites_mes(*_mes_anterior(ano, mes))

        # Doze meses para trás a partir do mês escolhido, para a série
        serie_ano, serie_mes = ano, mes
        for _ in range(11):
            serie_ano, serie_mes = _mes_anterior(serie_ano, serie_mes)
        serie_ini, _ = _limites_mes(serie_ano, serie_mes)

        todas = await self._todas(desde=serie_ini)
        pagas = [t for t in todas if t.status == "pago" and t.pago_em]

        def no(t_ini, t_fim, lista):
            return [t for t in lista if t_ini <= t.data < t_fim]

        do_mes = no(ini, fim, pagas)
        composicao = {"plano": 0.0, "locacao": 0.0, "avulso": 0.0}
        por_metodo = {"pix": 0.0, "cartao": 0.0, "boleto": 0.0}
        for t in do_mes:
            if t.categoria in composicao:
                composicao[t.categoria] += t.valor
            por_metodo[t.metodo] = por_metodo.get(t.metodo, 0.0) + t.valor

        pendentes = [t for t in todas if t.status == "pendente"]
        atrasados = [t for t in pendentes if t.data < agora]
        estornados = no(ini, fim, [t for t in todas if t.status == "estornado"])

        serie = []
        a, m = serie_ano, serie_mes
        for _ in range(12):
            s_ini, s_fim = _limites_mes(a, m)
            serie.append({"ano": a, "mes": m, "recebido": round(sum(t.valor for t in no(s_ini, s_fim, pagas)), 2)})
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)

        # Mês em andamento se compara com o MESMO trecho do mês anterior: 11
        # dias de outubro contra setembro inteiro sempre pareceria queda.
        em_andamento = ini <= agora < fim
        if em_andamento:
            decorrido = agora - ini
            ant_fim_comparavel = min(ant_ini + decorrido, ant_fim)
        else:
            ant_fim_comparavel = ant_fim

        return {
            "ano": ano,
            "mes": mes,
            "em_andamento": em_andamento,
            "recebido": round(sum(t.valor for t in do_mes), 2),
            "recebido_mes_anterior": round(sum(t.valor for t in no(ant_ini, ant_fim_comparavel, pagas)), 2),
            "pagamentos": len(do_mes),
            "a_receber": round(sum(t.valor for t in pendentes), 2),
            "pendentes": len(pendentes),
            "em_atraso": round(sum(t.valor for t in atrasados), 2),
            "atrasados": len(atrasados),
            "estornado": round(sum(t.valor for t in estornados), 2),
            "descontos": round(sum(t.desconto or 0 for t in do_mes), 2),
            "composicao": {k: round(v, 2) for k, v in composicao.items()},
            "por_metodo": {k: round(v, 2) for k, v in por_metodo.items()},
            "serie": serie,
        }

    async def transacoes(self, ano: int, mes: int, filtro: str = "todos", busca: str = "") -> list[dict]:
        """Transações do mês, da mais recente para a mais antiga.

        `pendentes` ignora o mês de propósito: mostra tudo o que está em aberto,
        que é o que o admin precisa cobrar.
        """
        ini, fim = _limites_mes(ano, mes)
        todas = await self._todas(desde=ini - timedelta(days=1))

        if filtro == "pendentes":
            escolhidas = [t for t in todas if t.status == "pendente"]
        else:
            escolhidas = [t for t in todas if ini <= t.data < fim and t.status != "pendente"]
            if filtro == "recebidos":
                escolhidas = [t for t in escolhidas if t.status == "pago"]
            elif filtro == "estornos":
                escolhidas = [t for t in escolhidas if t.status in ("estornado", "falhou")]

        termo = busca.strip().lower()
        if termo:
            escolhidas = [t for t in escolhidas if termo in t.pessoa.lower() or termo in t.titulo.lower()
                          or (t.cupom and termo in t.cupom.lower())]

        escolhidas.sort(key=lambda t: t.data, reverse=True)
        return [t.como_dict() for t in escolhidas]

    async def do_jogador(self, player_id: int, limite: int = 24) -> list[dict]:
        """Pagamentos de um associado: planos e reservas pelas quais respondeu."""
        consulta = _consulta_base().where(or_(
            Payment.subscription_id.in_(select(Subscription.id).where(Subscription.player_id == player_id)),
            Payment.booking_id.in_(select(Booking.id).where(Booking.jogador_responsavel_id == player_id)),
        ))
        linhas = (await self.db.execute(consulta)).scalars().all()
        transacoes = sorted((_para_transacao(p) for p in linhas), key=lambda t: t.data, reverse=True)
        return [t.como_dict() for t in transacoes[:limite]]
