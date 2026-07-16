"""
Ciclo de vida de partidas, pontos de ranking e Elo.

Pontos:
  Simples → vencedor +100, perdedor +30
  Simples W.O. → vencedor +100, perdedor −100
  Duplas → vencedor +50, perdedor +15
  Duplas W.O. → vencedor +50, perdedor −50

Elo:
  K = 32 (< 20 partidas), K = 16 (≥ 20)
  Duplas: K /= 2; rating médio por lado
  W.O.: NÃO afeta o rating

Classificação A/B/C/D:
  Top 25% = A · 25–50% = B · 50–75% = C · 75–100% = D
  Apenas jogadores com ≥ 5 partidas computadas.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSession
from app.models.booking import Booking, StatusReserva
from app.models.match import LadoPartida, Match, MatchParticipant, StatusPartida, TipoPartida
from app.models.player import NivelJogador, Player
from app.services.whatsapp_service import WhatsAppService


class MatchError(ValueError):
    pass


# ── Funções puras ──────────────────────────────────────────────────────────────

def _validar_placar(g_a: int, g_b: int, tb_a: int | None, tb_b: int | None) -> str:
    """Valida placar no formato Set Pro e retorna 'A' ou 'B' como vencedor."""
    if g_a == 8 and g_b == 8:
        if tb_a is None or tb_b is None:
            raise MatchError("Placar 8-8: informe o resultado do tiebreak")
        if max(tb_a, tb_b) < 7 or abs(tb_a - tb_b) < 2:
            raise MatchError("Tiebreak inválido: vencedor deve ter ≥ 7 pontos com diferença ≥ 2")
        return "A" if tb_a > tb_b else "B"

    if tb_a is not None or tb_b is not None:
        raise MatchError("Tiebreak só é válido quando o placar é 8-8")

    if g_a == 9 and g_b == 7:
        return "A"
    if g_a == 7 and g_b == 9:
        return "B"
    if g_a == 8 and g_b <= 6:
        return "A"
    if g_b == 8 and g_a <= 6:
        return "B"

    raise MatchError(
        f"Placar {g_a}-{g_b} inválido para Set Pro. "
        "Vencedor precisa ter 8 games (diferença ≥ 2), 9-7, ou 8-8 com tiebreak."
    )


def _expectativa(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def _k_factor(partidas: int, tipo: TipoPartida) -> float:
    k = 32.0 if partidas < 20 else 16.0
    return k / 2.0 if tipo == TipoPartida.DUPLAS else k


def _pontos_cfg(tipo: TipoPartida, is_wo: bool) -> dict[str, int]:
    if tipo == TipoPartida.SIMPLES:
        return {"vencedor": 100, "perdedor": -100} if is_wo else {"vencedor": 100, "perdedor": 30}
    return {"vencedor": 50, "perdedor": -50} if is_wo else {"vencedor": 50, "perdedor": 15}


# ── Serviço ───────────────────────────────────────────────────────────────────

class MatchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Consultas ──────────────────────────────────────────────────────────────

    async def listar_partidas(self, player: Player) -> list[Match]:
        stmt = (
            select(Match)
            .options(selectinload(Match.participantes).selectinload(MatchParticipant.convidado))
            .order_by(Match.data_hora.desc())
        )
        if not player.is_admin:
            stmt = (
                stmt
                .join(MatchParticipant, Match.id == MatchParticipant.match_id)
                .where(MatchParticipant.player_id == player.id)
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    # ── Ações ──────────────────────────────────────────────────────────────────

    async def submeter_placar(
        self,
        match_id: int,
        player: Player,
        games_a: int,
        games_b: int,
        tiebreak_a: int | None,
        tiebreak_b: int | None,
    ) -> Match:
        match = await self._get_match(match_id)
        if match is None:
            raise MatchError("Partida não encontrada")
        if match.avulso:
            raise MatchError("Jogo avulso não pontua no ranking e não aceita placar")
        if match.status != StatusPartida.AGENDADO:
            raise MatchError(f"Partida com status '{match.status.value}' não aceita placar")
        if datetime.now(timezone.utc) < match.data_hora:
            raise MatchError("A partida ainda não aconteceu")

        ids_participantes = {p.player_id for p in match.participantes}
        if player.id not in ids_participantes and not player.is_admin:
            raise MatchError("Você não é participante desta partida")

        lado_vencedor = _validar_placar(games_a, games_b, tiebreak_a, tiebreak_b)

        match.status = StatusPartida.REALIZADO
        match.lado_vencedor = lado_vencedor
        match.placar = {
            "games_A": games_a,
            "games_B": games_b,
            "tiebreak_A": tiebreak_a,
            "tiebreak_B": tiebreak_b,
        }

        await self._processar_resultado(match, is_wo=False)
        await self.db.commit()
        await self.db.refresh(match)
        await self._notificar_resultado(match)
        return match

    async def registrar_wo(self, match_id: int, lado_wo: str, player: Player) -> Match:
        if lado_wo not in ("A", "B"):
            raise MatchError("lado_wo deve ser 'A' ou 'B'")
        if not player.is_admin:
            raise MatchError("Apenas administradores podem registrar W.O.")

        match = await self._get_match(match_id)
        if match is None:
            raise MatchError("Partida não encontrada")
        if match.avulso:
            raise MatchError("Jogo avulso não pontua no ranking e não aceita W.O.")
        if match.status != StatusPartida.AGENDADO:
            raise MatchError(f"Partida com status '{match.status.value}' não pode receber W.O.")

        match.status = StatusPartida.WO
        match.lado_vencedor = "B" if lado_wo == "A" else "A"
        await self._processar_resultado(match, is_wo=True)
        await self.db.commit()
        await self.db.refresh(match)
        await self._notificar_resultado(match)
        return match

    async def cancelar_por_jogador(self, match_id: int, player: Player) -> Match:
        """Qualquer participante pode cancelar uma partida futura ainda agendada."""
        match = await self._get_match(match_id)
        if match is None:
            raise MatchError("Partida não encontrada")
        if match.status != StatusPartida.AGENDADO:
            raise MatchError("Só é possível cancelar partidas com status Agendado")
        if match.data_hora <= datetime.now(timezone.utc):
            raise MatchError("Não é possível cancelar uma partida que já iniciou")
        ids_participantes = {p.player_id for p in match.participantes}
        if not player.is_admin and player.id not in ids_participantes:
            raise MatchError("Você não é participante desta partida")

        match.status = StatusPartida.CANCELADO_SEM_PLACAR

        # Libera o slot na agenda
        booking_res = await self.db.execute(
            select(Booking).where(Booking.match_id == match_id)
        )
        booking = booking_res.scalar_one_or_none()
        if booking:
            booking.status = StatusReserva.CANCELADA

        await self.db.commit()
        await self.db.refresh(match)
        return match

    async def cancelar_sem_placar(self, match_id: int, player: Player) -> Match:
        if not player.is_admin:
            raise MatchError("Apenas administradores podem cancelar partidas sem placar")

        match = await self._get_match(match_id)
        if match is None:
            raise MatchError("Partida não encontrada")
        if match.status != StatusPartida.AGENDADO:
            raise MatchError(f"Partida com status '{match.status.value}' não pode ser cancelada sem placar")

        match.status = StatusPartida.CANCELADO_SEM_PLACAR
        await self.db.commit()
        await self.db.refresh(match)
        return match

    async def recalcular_classificacao(self) -> int:
        """Reclassifica A/B/C/D por percentil. Retorna número de jogadores elegíveis."""
        await self.db.execute(
            update(Player)
            .where(Player.partidas_computadas_rating < 5)
            .values(nivel=NivelJogador.NAO_CLASSIFICADO)
        )

        result = await self.db.execute(
            select(Player)
            .where(Player.partidas_computadas_rating >= 5)
            .order_by(Player.rating_atual.desc())
        )
        elegíveis = list(result.scalars().all())
        n = len(elegíveis)

        for i, p in enumerate(elegíveis):
            pct = i / n
            if pct < 0.25:
                p.nivel = NivelJogador.A
            elif pct < 0.50:
                p.nivel = NivelJogador.B
            elif pct < 0.75:
                p.nivel = NivelJogador.C
            else:
                p.nivel = NivelJogador.D

        await self.db.commit()
        return n

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_match(self, match_id: int) -> Match | None:
        result = await self.db.execute(
            select(Match)
            .where(Match.id == match_id)
            .options(selectinload(Match.participantes).selectinload(MatchParticipant.convidado))
        )
        return result.scalar_one_or_none()

    async def _processar_resultado(self, match: Match, is_wo: bool) -> None:
        lado_a = [p for p in match.participantes if p.lado == LadoPartida.A]
        lado_b = [p for p in match.participantes if p.lado == LadoPartida.B]

        # Carrega todos os players num único SELECT
        player_ids = [p.player_id for p in match.participantes]
        result = await self.db.execute(select(Player).where(Player.id.in_(player_ids)))
        by_id: dict[int, Player] = {p.id: p for p in result.scalars().all()}

        # Snapshot rating_antes
        for part in match.participantes:
            part.rating_antes = by_id[part.player_id].rating_atual

        # Pontos de ranking
        cfg = _pontos_cfg(match.tipo, is_wo)
        vencedor = match.lado_vencedor
        for part in lado_a:
            pts = cfg["vencedor"] if vencedor == "A" else cfg["perdedor"]
            part.pontos_atribuidos = pts
            by_id[part.player_id].pontos_ranking_temporada_atual += pts
        for part in lado_b:
            pts = cfg["vencedor"] if vencedor == "B" else cfg["perdedor"]
            part.pontos_atribuidos = pts
            by_id[part.player_id].pontos_ranking_temporada_atual += pts

        if is_wo:
            return  # W.O. não afeta o rating

        # Elo
        if match.tipo == TipoPartida.SIMPLES:
            pa = by_id[lado_a[0].player_id]
            pb = by_id[lado_b[0].player_id]
            e_a = _expectativa(pa.rating_atual, pb.rating_atual)
            s_a = 1.0 if vencedor == "A" else 0.0

            ka = _k_factor(pa.partidas_computadas_rating, match.tipo)
            kb = _k_factor(pb.partidas_computadas_rating, match.tipo)
            pa.rating_atual = max(0.0, pa.rating_atual + ka * (s_a - e_a))
            pb.rating_atual = max(0.0, pb.rating_atual + kb * ((1 - s_a) - (1 - e_a)))
            pa.partidas_computadas_rating += 1
            pb.partidas_computadas_rating += 1
            lado_a[0].rating_depois = pa.rating_atual
            lado_b[0].rating_depois = pb.rating_atual

        else:
            players_a = [by_id[p.player_id] for p in lado_a]
            players_b = [by_id[p.player_id] for p in lado_b]
            avg_a = sum(p.rating_atual for p in players_a) / len(players_a)
            avg_b = sum(p.rating_atual for p in players_b) / len(players_b)
            e_a = _expectativa(avg_a, avg_b)
            s_a = 1.0 if vencedor == "A" else 0.0

            for part, pl in list(zip(lado_a, players_a)) + list(zip(lado_b, players_b)):
                s = s_a if part.lado == LadoPartida.A else 1 - s_a
                e = e_a if part.lado == LadoPartida.A else 1 - e_a
                k = _k_factor(pl.partidas_computadas_rating, match.tipo)
                pl.rating_atual = max(0.0, pl.rating_atual + k * (s - e))
                pl.partidas_computadas_rating += 1
                part.rating_depois = pl.rating_atual

    async def _notificar_resultado(self, match: Match) -> None:
        try:
            lado_a = [p for p in match.participantes if p.lado == LadoPartida.A]
            lado_b = [p for p in match.participantes if p.lado == LadoPartida.B]
            player_ids = [p.player_id for p in match.participantes]
            res = await self.db.execute(select(Player).where(Player.id.in_(player_ids)))
            by_id = {p.id: p for p in res.scalars().all()}

            placar_str = ""
            if match.placar:
                g_a = match.placar.get("games_A", "?")
                g_b = match.placar.get("games_B", "?")
                tb_a = match.placar.get("tiebreak_A")
                tb_b = match.placar.get("tiebreak_B")
                placar_str = f"{g_a}-{g_b}" + (f" (TB {tb_a}-{tb_b})" if tb_a is not None else "")

            wa = WhatsAppService(self.db)
            for part in match.participantes:
                player = by_id.get(part.player_id)
                if not player:
                    continue
                lado_adv = lado_b if part.lado == LadoPartida.A else lado_a
                adv = " / ".join(by_id[p.player_id].nome.split()[0] for p in lado_adv if p.player_id in by_id)
                ganhou = match.lado_vencedor == part.lado.value
                await wa.notificar_resultado(
                    player_id=player.id,
                    nome=player.nome,
                    telefone=player.telefone,
                    adversario=adv,
                    placar=placar_str,
                    ganhou=ganhou,
                    pontos_delta=part.pontos_atribuidos or 0,
                )
        except Exception:
            pass
