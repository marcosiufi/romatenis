"""Popula o banco LOCAL com dados de exemplo para testar o sistema.

Uso (dentro do container do ambiente local):

    docker compose -f docker-compose.local.yml exec api python scripts/seed_local.py

Sem dados, a tela local fica vazia e não dá para avaliar layout, estados nem o
financeiro. Este script cria um clube plausível: associados em todos os
estados de assinatura, oito meses de recebimentos (planos, locações e jogos
avulsos), partidas jogadas e marcadas, inadimplência, estorno, cupons e lista
de espera.

**Recusa rodar fora de `ENVIRONMENT=development`.** Ele cria contas com senha
conhecida — em produção isso seria uma porta aberta.

As credenciais de teste estão nas constantes abaixo e em `docs/LOCAL.md`.
"""
import asyncio
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.auth import hash_password  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.booking import Booking, StatusReserva, TipoReserva  # noqa: E402
from app.models.configuracao import Configuracao  # noqa: E402
from app.models.convidado import Convidado  # noqa: E402
from app.models.cupom import Cupom  # noqa: E402
from app.models.lista_espera import ListaEspera, StatusListaEspera  # noqa: E402
from app.models.match import LadoPartida, Match, MatchParticipant, StatusPartida, TipoPartida  # noqa: E402
from app.models.payment import MetodoPagamento, Payment, StatusPagamento  # noqa: E402
from app.models.player import NivelJogador, Player, StatusJogador  # noqa: E402
from app.models.season import Season, StatusTemporada  # noqa: E402
from app.models.subscription import FormaPagamento, PlanoAssinatura, StatusAssinatura, Subscription  # noqa: E402

FUSO = ZoneInfo("America/Sao_Paulo")

# ── Credenciais de TESTE (só existem no banco local) ─────────────────────────
# Subdomínio da própria marca, sem MX: passa no validador de e-mail (que
# recusa `.local`, nome reservado) e nenhuma mensagem sai daqui para alguém.
EMAIL_ADMIN = "admin@teste.romatenis.com.br"
EMAIL_ASSOCIADO = "ana@teste.romatenis.com.br"
SENHA_TESTE = "roma-local-2026"

PRECOS = {
    PlanoAssinatura.MENSAL: 89.90,
    PlanoAssinatura.TRIMESTRAL: 239.90,
    PlanoAssinatura.SEMESTRAL: 449.90,
    PlanoAssinatura.ANUAL: 839.90,
}
MESES_DO_PLANO = {
    PlanoAssinatura.MENSAL: 1,
    PlanoAssinatura.TRIMESTRAL: 3,
    PlanoAssinatura.SEMESTRAL: 6,
    PlanoAssinatura.ANUAL: 12,
}
PRECO_LOCACAO = 120.00
PRECO_AVULSO = 60.00

# (nome, apelido, nível, rating, pontos, partidas, plano, situação)
ASSOCIADOS = [
    ("Ana Prado",          "Aninha",   "A", 1612, 148, 23, PlanoAssinatura.MENSAL,     "ativa"),
    ("Bruno Reis",         "Brunão",   "A", 1588, 131, 21, PlanoAssinatura.TRIMESTRAL, "ativa"),
    ("Carla Mendes",       None,       "A", 1541, 120, 19, PlanoAssinatura.ANUAL,      "ativa"),
    ("Diego Arantes",      "Didi",     "B", 1476, 104, 18, PlanoAssinatura.MENSAL,     "ativa"),
    ("Eduarda Lins",       "Duda",     "B", 1452,  98, 17, PlanoAssinatura.SEMESTRAL,  "ativa"),
    ("Felipe Moura",       None,       "B", 1430,  91, 16, PlanoAssinatura.MENSAL,     "ativa"),
    ("Gabriela Tavares",   "Gabi",     "B", 1398,  83, 15, PlanoAssinatura.TRIMESTRAL, "ativa"),
    ("Henrique Sales",     "Rique",    "C", 1344,  70, 14, PlanoAssinatura.MENSAL,     "ativa"),
    ("Isabela Fontes",     "Isa",      "C", 1312,  62, 12, PlanoAssinatura.MENSAL,     "inadimplente"),
    ("João Pedro Queiroz", "JP",       "C", 1290,  55, 11, PlanoAssinatura.TRIMESTRAL, "ativa"),
    ("Karina Lobo",        None,       "D", 1215,  38,  9, PlanoAssinatura.MENSAL,     "ativa"),
    ("Lucas Barreto",      "Luquinha", "D", 1188,  31,  8, PlanoAssinatura.MENSAL,     "pendente"),
    ("Marina Coutinho",    "Mari",     "nao_classificado", 1000, 0, 2, PlanoAssinatura.MENSAL, "expirada"),
    ("Nicolas Ferraz",     None,       "nao_classificado", 1000, 0, 0, PlanoAssinatura.MENSAL, "sem_plano"),
]

CLIENTES_LOCACAO = [
    "Rodrigo Almeida", "Patrícia Nogueira", "Grupo Tênis Sábado", "Thiago Vasconcelos",
    "Fernanda Ribeiro", "Academia Ace", "Marcelo Duarte", "Vanessa Prado",
    "Leonardo Castro", "Camila Freitas",
]

CONVIDADOS = [
    ("Otávio Pinheiro", "52998224725"),
    ("Renata Campos",   "11144477735"),
    ("Sérgio Lima",     "39053344705"),
]


class Agenda:
    """Evita sobreposição de reservas ativas.

    O banco recusa duas reservas ativas no mesmo horário (constraint
    `bookings_sem_sobreposicao`, migration 0030) — o seed precisa respeitar a
    mesma regra que o sistema.
    """

    def __init__(self) -> None:
        self.ocupados: set[datetime] = set()

    def reservar(self, dia: date, hora: int) -> datetime | None:
        inicio = datetime.combine(dia, time(hora), tzinfo=FUSO).astimezone(timezone.utc)
        if inicio in self.ocupados:
            return None
        self.ocupados.add(inicio)
        return inicio

    def primeiro_livre(self, dia: date, horas: list[int]) -> datetime | None:
        for h in horas:
            r = self.reservar(dia, h)
            if r:
                return r
        return None


def _cpf_valido(base9: str) -> str:
    """Completa um CPF com os dígitos verificadores corretos."""
    nums = [int(c) for c in base9]
    for _ in range(2):
        peso = len(nums) + 1
        soma = sum(n * (peso - i) for i, n in enumerate(nums))
        dv = (soma * 10) % 11
        nums.append(0 if dv == 10 else dv)
    return "".join(map(str, nums))


async def main() -> None:
    if settings.ENVIRONMENT != "development":
        print("Recusado: este script só roda com ENVIRONMENT=development.")
        print("Ele cria contas com senha conhecida — nunca rode em produção.")
        sys.exit(1)

    random.seed(42)   # mesmos dados a cada execução: dá para comparar telas
    agora = datetime.now(timezone.utc)
    hoje = agora.astimezone(FUSO).date()
    senha = hash_password(SENHA_TESTE)

    async with AsyncSessionLocal() as db:
        if (await db.execute(select(Player).where(Player.email == EMAIL_ADMIN))).scalar_one_or_none():
            print("O banco local já tem os dados de exemplo.")
            print("Para recriar do zero:")
            print("  docker compose -f docker-compose.local.yml down -v")
            print("  (e suba de novo, migrations e seed)")
            return

        # ── Configuração: tudo aberto, como num clube em operação ───────────
        cfg = await Configuracao.get(db)
        cfg.reservas_ativas = True
        cfg.contratacao_planos_ativa = True

        # ── Temporadas ──────────────────────────────────────────────────────
        inicio_temp = datetime(hoje.year, hoje.month, 1, tzinfo=FUSO) - timedelta(days=40)
        anterior = Season(
            data_inicio=inicio_temp - timedelta(days=92),
            data_fim=inicio_temp - timedelta(seconds=1),
            status=StatusTemporada.ENCERRADA,
        )
        atual = Season(
            data_inicio=inicio_temp,
            data_fim=inicio_temp + timedelta(days=91),
            status=StatusTemporada.ATIVA,
        )
        db.add_all([anterior, atual])

        # ── Pessoas ─────────────────────────────────────────────────────────
        admin = Player(
            nome="Marco Siufi", apelido="Marco", telefone="16990000000",
            email=EMAIL_ADMIN, senha_hash=senha, is_admin=True,
            status=StatusJogador.ATIVO.value, contrato_assinado=True,
        )
        db.add(admin)

        jogadores: list[Player] = []
        for i, (nome, apelido, nivel, rating, pontos, partidas, _plano, situacao) in enumerate(ASSOCIADOS):
            primeiro = nome.split()[0].lower()
            email = EMAIL_ASSOCIADO if i == 0 else f"{primeiro}.{i}@teste.romatenis.com.br"
            status = {
                "ativa": StatusJogador.ATIVO, "inadimplente": StatusJogador.PAGAMENTO,
                "pendente": StatusJogador.ASSINATURA, "expirada": StatusJogador.RENOVACAO,
                "sem_plano": StatusJogador.INATIVO,
            }[situacao]
            p = Player(
                nome=nome, apelido=apelido, email=email,
                telefone=f"169910{i:05d}", senha_hash=senha,
                nivel=NivelJogador(nivel), rating_atual=float(rating),
                pontos_ranking_temporada_atual=pontos,
                partidas_computadas_rating=partidas,
                status=status.value,
                contrato_assinado=situacao in ("ativa", "inadimplente", "expirada"),
                cpf=_cpf_valido(f"{100000000 + i * 7919:09d}"),
                data_nascimento=date(1980 + i, (i % 12) + 1, (i % 27) + 1),
                rua="Rua das Palmeiras", numero=str(100 + i * 12), bairro="Jardim Botânico",
                cidade="Ribeirão Preto", estado="SP", cep="14021-000",
                data_cadastro=agora - timedelta(days=260 - i * 9),
            )
            jogadores.append(p)
        db.add_all(jogadores)
        await db.flush()

        anterior.ranking_final = [
            {"posicao": 1, "player_id": jogadores[1].id, "nome": jogadores[1].nome, "pontos": 162},
            {"posicao": 2, "player_id": jogadores[0].id, "nome": jogadores[0].nome, "pontos": 155},
            {"posicao": 3, "player_id": jogadores[2].id, "nome": jogadores[2].nome, "pontos": 140},
        ]

        # ── Assinaturas e oito meses de recebimentos ────────────────────────
        pagamentos = 0
        for p, (_n, _a, _nv, _r, _pt, _pa, plano, situacao) in zip(jogadores, ASSOCIADOS):
            if situacao == "sem_plano":
                continue
            meses = MESES_DO_PLANO[plano]
            preco = PRECOS[plano]
            forma = random.choice([FormaPagamento.PIX_AVISTA, FormaPagamento.PIX_AVISTA,
                                   FormaPagamento.CARTAO_PARCELADO])
            # Ciclos para trás até ~8 meses: é o histórico que o gráfico mostra.
            ciclos = max(1, 8 // meses)
            fim_ciclo = datetime.combine(hoje, time(23, 59), tzinfo=FUSO).astimezone(timezone.utc)
            if situacao == "ativa":
                fim_ciclo += timedelta(days=random.randint(6, 25))
            elif situacao == "expirada":
                fim_ciclo -= timedelta(days=4)
            elif situacao == "inadimplente":
                fim_ciclo += timedelta(days=2)

            for c in range(ciclos):
                f = fim_ciclo - timedelta(days=30 * meses * c)
                ini = f - timedelta(days=30 * meses)
                ultimo = c == 0
                status_sub = {
                    "ativa": StatusAssinatura.ATIVA, "inadimplente": StatusAssinatura.INADIMPLENTE,
                    "pendente": StatusAssinatura.PENDENTE, "expirada": StatusAssinatura.EXPIRADA,
                }[situacao] if ultimo else StatusAssinatura.EXPIRADA
                sub = Subscription(
                    player_id=p.id, plano=plano,
                    valor_mensal=round(preco / meses, 2), valor_total_ciclo=preco,
                    forma_pagamento=forma, parcelas=1,
                    status=status_sub, data_inicio_ciclo=ini, data_expiracao=f,
                )
                db.add(sub)
                await db.flush()

                pix = forma == FormaPagamento.PIX_AVISTA
                valor = round(preco * (0.95 if pix else 1), 2)
                metodo = MetodoPagamento.PIX if pix else MetodoPagamento.CARTAO
                pendente = ultimo and situacao in ("inadimplente", "pendente")
                desconto, cupom = None, None
                if c == ciclos - 1 and p is jogadores[3]:
                    cupom, desconto = "BEMVINDO10", round(valor * 0.10, 2)
                    valor = round(valor - desconto, 2)
                db.add(Payment(
                    subscription_id=sub.id, valor=valor, metodo=metodo,
                    status=StatusPagamento.PENDENTE if pendente else StatusPagamento.PAGO,
                    data_pagamento=None if pendente else ini + timedelta(hours=random.randint(1, 40)),
                    cupom_codigo=cupom, valor_desconto=desconto,
                ))
                pagamentos += 1

        # ── Agenda: partidas, locações e jogos avulsos ──────────────────────
        agenda = Agenda()
        horas_ranking = [6, 7, 17, 18, 19, 20, 21]
        horas_comercial = [8, 9, 10, 11, 14, 15, 16]

        # Partidas jogadas (últimas 6 semanas)
        realizadas = 0
        for d in range(42, 0, -1):
            dia = hoje - timedelta(days=d)
            for _ in range(random.randint(0, 2)):
                inicio = agenda.primeiro_livre(dia, random.sample(horas_ranking, len(horas_ranking)))
                if inicio is None:
                    continue
                a, b = random.sample(jogadores[:11], 2)
                vencedor = random.choice(["A", "B"])
                ga, gb = (8, random.randint(2, 6)) if vencedor == "A" else (random.randint(2, 6), 8)
                status = StatusPartida.WO if random.random() < 0.06 else StatusPartida.REALIZADO
                m = Match(
                    tipo=TipoPartida.SIMPLES, status=status, data_hora=inicio,
                    season_id=atual.id if inicio >= atual.data_inicio else anterior.id,
                    placar=None if status == StatusPartida.WO else
                        {"games_A": ga, "games_B": gb, "tiebreak_A": None, "tiebreak_B": None},
                    lado_vencedor=vencedor,
                )
                db.add(m)
                await db.flush()
                for jog, lado in ((a, LadoPartida.A), (b, LadoPartida.B)):
                    ganhou = lado.value == vencedor
                    db.add(MatchParticipant(
                        match_id=m.id, player_id=jog.id, lado=lado,
                        rating_antes=jog.rating_atual,
                        rating_depois=jog.rating_atual + (12 if ganhou else -12),
                        pontos_atribuidos=10 if ganhou else 3,
                    ))
                db.add(Booking(
                    data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
                    tipo=TipoReserva.RANKING, status=StatusReserva.CONFIRMADA,
                    jogador_responsavel_id=a.id, match_id=m.id,
                ))
                realizadas += 1

        # Próximas partidas — a Ana tem uma simples e uma dupla marcadas,
        # para a tela "Partidas" e o painel de uso semanal terem conteúdo.
        ana, bruno, carla, diego = jogadores[0], jogadores[1], jogadores[2], jogadores[3]
        marcadas = [
            (1, TipoPartida.SIMPLES, [ana], [bruno]),
            (3, TipoPartida.DUPLAS, [ana, diego], [carla, jogadores[4]]),
            (2, TipoPartida.SIMPLES, [jogadores[5]], [jogadores[6]]),
            (4, TipoPartida.SIMPLES, [jogadores[7]], [jogadores[9]]),
        ]
        for dias, tipo, lado_a, lado_b in marcadas:
            inicio = agenda.primeiro_livre(hoje + timedelta(days=dias), [19, 20, 18, 21, 7])
            m = Match(tipo=tipo, status=StatusPartida.AGENDADO, data_hora=inicio, season_id=atual.id)
            db.add(m)
            await db.flush()
            for jog in lado_a:
                db.add(MatchParticipant(match_id=m.id, player_id=jog.id, lado=LadoPartida.A))
            for jog in lado_b:
                db.add(MatchParticipant(match_id=m.id, player_id=jog.id, lado=LadoPartida.B))
            db.add(Booking(
                data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
                tipo=TipoReserva.RANKING, status=StatusReserva.CONFIRMADA,
                jogador_responsavel_id=lado_a[0].id, match_id=m.id,
            ))

        # Partida passada ainda sem placar — aparece em "Sem placar" no painel
        inicio = agenda.primeiro_livre(hoje - timedelta(days=1), [19, 20])
        m = Match(tipo=TipoPartida.SIMPLES, status=StatusPartida.AGENDADO, data_hora=inicio, season_id=atual.id)
        db.add(m)
        await db.flush()
        db.add(MatchParticipant(match_id=m.id, player_id=ana.id, lado=LadoPartida.A))
        db.add(MatchParticipant(match_id=m.id, player_id=carla.id, lado=LadoPartida.B))
        db.add(Booking(
            data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
            tipo=TipoReserva.RANKING, status=StatusReserva.CONFIRMADA,
            jogador_responsavel_id=ana.id, match_id=m.id,
        ))

        # Locações avulsas: oito meses, mais nos fins de semana
        locacoes = 0
        for d in range(240, -10, -1):
            dia = hoje - timedelta(days=d)
            chance = 0.55 if dia.weekday() >= 5 else 0.22
            if random.random() > chance:
                continue
            horas = horas_comercial if dia.weekday() < 5 else [8, 9, 10, 15, 16]
            inicio = agenda.primeiro_livre(dia, random.sample(horas, len(horas)))
            if inicio is None:
                continue
            futura = inicio > agora
            cliente = random.choice(CLIENTES_LOCACAO)
            bk = Booking(
                data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
                tipo=TipoReserva.LOCACAO_AVULSA, status=StatusReserva.CONFIRMADA,
                cliente_locacao_nome=cliente,
                cliente_locacao_telefone=f"1698{random.randint(1000000, 9999999)}",
                valor=PRECO_LOCACAO,
            )
            db.add(bk)
            await db.flush()
            # Um estorno e uma falha no histórico — o financeiro precisa mostrar
            # esses estados também, não só o caminho feliz.
            if locacoes == 7:
                st = StatusPagamento.ESTORNADO
            elif locacoes == 15:
                st = StatusPagamento.FALHOU
            else:
                st = StatusPagamento.PAGO
            db.add(Payment(
                booking_id=bk.id, valor=PRECO_LOCACAO,
                metodo=random.choice([MetodoPagamento.PIX, MetodoPagamento.PIX, MetodoPagamento.CARTAO]),
                status=st,
                # Pago antes do jogo, mas nunca no futuro: locação marcada para a
                # semana que vem foi paga até agora, não no dia do jogo.
                data_pagamento=min(inicio - timedelta(days=random.randint(1, 5)),
                                   agora - timedelta(hours=random.randint(1, 30)))
                               if st != StatusPagamento.FALHOU else None,
            ))
            locacoes += 1

        # Jogos avulsos com convidado
        convidados = []
        for nome, cpf in CONVIDADOS:
            cv = Convidado(nome=nome, cpf=cpf, whatsapp="16999990000", data_nascimento=date(1990, 5, 10))
            db.add(cv)
            convidados.append(cv)
        await db.flush()

        avulsos = 0
        for d in (55, 38, 24, 12, 5):
            dia = hoje - timedelta(days=d)
            inicio = agenda.primeiro_livre(dia, [8, 9, 10, 11])
            if inicio is None:
                continue
            anfitriao = random.choice(jogadores[:8])
            cv = random.choice(convidados)
            m = Match(
                tipo=TipoPartida.SIMPLES, status=StatusPartida.REALIZADO, data_hora=inicio,
                avulso=True, placar={"games_A": 8, "games_B": 6, "tiebreak_A": None, "tiebreak_B": None},
                lado_vencedor="A",
            )
            db.add(m)
            await db.flush()
            db.add(MatchParticipant(match_id=m.id, player_id=anfitriao.id, lado=LadoPartida.A))
            db.add(MatchParticipant(match_id=m.id, convidado_id=cv.id, lado=LadoPartida.B))
            bk = Booking(
                data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
                tipo=TipoReserva.JOGO_AVULSO, status=StatusReserva.CONFIRMADA,
                jogador_responsavel_id=anfitriao.id, match_id=m.id, valor=PRECO_AVULSO,
            )
            db.add(bk)
            await db.flush()
            db.add(Payment(
                booking_id=bk.id, valor=PRECO_AVULSO, metodo=MetodoPagamento.PIX,
                status=StatusPagamento.PAGO, data_pagamento=inicio - timedelta(minutes=30),
            ))
            avulsos += 1

        # ── Cupons ──────────────────────────────────────────────────────────
        db.add_all([
            Cupom(codigo="BEMVINDO10", percentual=10, descricao="Primeira mensalidade",
                  max_usos=50, usos=3, ativo=True,
                  validade_fim=agora + timedelta(days=60)),
            Cupom(codigo="PARCEIRO15", percentual=15, descricao="Empresas parceiras",
                  ativo=True),
            Cupom(codigo="VERAO20", percentual=20, descricao="Campanha de verão",
                  max_usos=30, usos=30, ativo=True,
                  validade_inicio=agora - timedelta(days=200), validade_fim=agora - timedelta(days=110)),
        ])

        # ── Lista de espera ─────────────────────────────────────────────────
        extras = []
        for i, nome in enumerate(["Otávio Rezende", "Paula Siqueira"]):
            pe = Player(
                nome=nome, email=f"espera.{i}@teste.romatenis.com.br", telefone=f"169920{i:05d}",
                senha_hash=senha, status=StatusJogador.INATIVO.value,
            )
            db.add(pe)
            extras.append(pe)
        await db.flush()
        db.add(ListaEspera(player_id=extras[0].id, status=StatusListaEspera.AGUARDANDO,
                           data_inscricao=agora - timedelta(days=12)))
        db.add(ListaEspera(player_id=extras[1].id, status=StatusListaEspera.AGUARDANDO,
                           data_inscricao=agora - timedelta(days=4)))

        await db.commit()

    print("Dados de exemplo criados:")
    print(f"  {len(jogadores)} associados, {pagamentos} pagamentos de plano,")
    print(f"  {realizadas} partidas jogadas, {locacoes} locações, {avulsos} jogos avulsos.")
    print()
    print("Acesse:")
    print("  App do associado  http://localhost:8100/app/")
    print("  Painel admin      http://localhost:8100/admin/")
    print("Credenciais de teste: ver docs/LOCAL.md")


if __name__ == "__main__":
    asyncio.run(main())
