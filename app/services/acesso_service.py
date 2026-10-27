"""Controle de acesso à quadra.

O servidor mantém o *estado desejado* — quem pode entrar e em que intervalo — e
o agente que roda na quadra reconcilia os leitores com esse estado. Nada aqui
fala com o hardware; ver `agente-acesso/` e o docstring de
`app.models.acesso`.

Três origens de pessoa desembocam numa mesma `CredencialAcesso`:

- **associado do ranking** — usa a foto do perfil (`Player.foto_url`);
- **convidado de jogo avulso** — manda a selfie por um link com token;
- **cliente de locação avulsa** — idem, preso à reserva, porque não tem conta.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.imagens import apagar_foto_antiga, nome_de_foto
from app.models.acesso import (
    ComandoAcesso,
    CredencialAcesso,
    DispositivoAcesso,
    EventoAcesso,
    JanelaAcesso,
    StatusComando,
    StatusCredencial,
    StatusJanela,
    TipoEventoAcesso,
)
from app.models.booking import Booking, StatusReserva, TipoReserva
from app.models.configuracao import Configuracao
from app.models.match import Match

logger = logging.getLogger(__name__)

# Diretório físico servido em /uploads — o agente baixa as fotos por HTTP.
_DIR_UPLOADS = "uploads"

# Quanto tempo à frente o estado enviado ao agente enxerga. Precisa cobrir uma
# queda de internet longa sem inchar o payload: com 7 dias, a quadra opera uma
# semana inteira offline com o que já sincronizou.
HORIZONTE_JANELAS = timedelta(days=7)

# Janela terminada há mais que isto é descartada do estado.
RETENCAO_JANELAS = timedelta(hours=6)


class AcessoError(ValueError):
    """Erro de regra do controle de acesso."""


class AcessoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Credenciais ──────────────────────────────────────────────────────────

    async def credencial_do_player(self, player) -> CredencialAcesso:
        """Credencial do associado, criada na primeira necessidade.

        A foto vem do perfil: o associado já tem tela para trocá-la, então não
        faz sentido pedir uma segunda selfie só para o portão.
        """
        cred = (
            await self.db.execute(
                select(CredencialAcesso).where(CredencialAcesso.player_id == player.id)
            )
        ).scalar_one_or_none()
        if cred is None:
            cred = CredencialAcesso(player_id=player.id, nome=player.nome, id_dispositivo="")
            self.db.add(cred)
            await self.db.flush()
            cred.id_dispositivo = _id_dispositivo(cred.id)
        cred.nome = player.nome
        self._aplicar_foto(cred, player.foto_url)
        return cred

    async def credencial_do_convidado(self, convidado) -> CredencialAcesso:
        cred = (
            await self.db.execute(
                select(CredencialAcesso).where(CredencialAcesso.convidado_id == convidado.id)
            )
        ).scalar_one_or_none()
        if cred is None:
            cred = CredencialAcesso(
                convidado_id=convidado.id,
                nome=convidado.nome,
                id_dispositivo="",
                token_selfie=secrets.token_urlsafe(32),
            )
            self.db.add(cred)
            await self.db.flush()
            cred.id_dispositivo = _id_dispositivo(cred.id)
        cred.nome = convidado.nome
        self._aplicar_foto(cred, convidado.foto_url)
        return cred

    async def credencial_da_locacao(self, booking: Booking) -> CredencialAcesso:
        """Cliente que alugou a quadra. Não tem conta: a credencial é da reserva."""
        cred = (
            await self.db.execute(
                select(CredencialAcesso).where(CredencialAcesso.booking_id == booking.id)
            )
        ).scalar_one_or_none()
        if cred is None:
            cred = CredencialAcesso(
                booking_id=booking.id,
                nome=booking.cliente_locacao_nome or "Cliente da locação",
                id_dispositivo="",
                token_selfie=secrets.token_urlsafe(32),
            )
            self.db.add(cred)
            await self.db.flush()
            cred.id_dispositivo = _id_dispositivo(cred.id)
        if booking.cliente_locacao_nome:
            cred.nome = booking.cliente_locacao_nome
        return cred

    def _aplicar_foto(self, cred: CredencialAcesso, foto_url: str | None) -> None:
        """Sincroniza a foto da credencial com a da origem.

        O hash é do conteúdo, não da URL: o upload sobrescreve o arquivo mantendo
        o nome, então comparar URL não detectaria a troca da selfie.
        """
        if not foto_url:
            if cred.status != StatusCredencial.SINCRONIZADA:
                cred.status = StatusCredencial.PENDENTE_FOTO
            return

        novo_hash = _hash_do_upload(foto_url)
        if novo_hash is None:
            # Registro aponta para arquivo que sumiu do disco. Não apaga o que já
            # está no leitor — só marca para o painel mostrar o problema.
            cred.status = StatusCredencial.ERRO
            cred.erro = "Arquivo da foto não encontrado no servidor."
            return

        if cred.foto_hash != novo_hash:
            cred.foto_url = foto_url
            cred.foto_hash = novo_hash
            cred.status = StatusCredencial.PENDENTE_ENVIO
            cred.erro = None
        elif cred.status in (StatusCredencial.PENDENTE_FOTO, StatusCredencial.REMOVIDA):
            cred.foto_url = foto_url
            cred.status = StatusCredencial.PENDENTE_ENVIO

    async def dados_do_link(self, token: str) -> CredencialAcesso:
        """Credencial de um link de selfie, só enquanto ele vale."""
        cred = (
            await self.db.execute(
                select(CredencialAcesso).where(CredencialAcesso.token_selfie == token)
            )
        ).scalar_one_or_none()
        if cred is None or not await self._link_valido(cred):
            raise AcessoError("Link inválido ou expirado.")
        return cred

    async def _link_valido(self, cred: CredencialAcesso) -> bool:
        """O link vale enquanto houver jogo por vir.

        Depois disso, aceitar a foto não liberaria nada agora — mas cadastraria
        outro rosto para o próximo jogo dessa pessoa, por quem tivesse guardado
        o link. Um link antigo não pode fazer isso.
        """
        agora = datetime.now(timezone.utc)
        janela = await self.db.scalar(
            select(JanelaAcesso.id)
            .where(
                JanelaAcesso.credencial_id == cred.id,
                JanelaAcesso.status == StatusJanela.ATIVA,
                JanelaAcesso.fim >= agora,
            )
            .limit(1)
        )
        return janela is not None

    async def atualizar_foto_do_player(self, player) -> None:
        """Foto do perfil trocada: a credencial do portão, se existir, acompanha."""
        cred = (
            await self.db.execute(
                select(CredencialAcesso).where(CredencialAcesso.player_id == player.id)
            )
        ).scalar_one_or_none()
        if cred is None:
            return
        self._aplicar_foto(cred, player.foto_url)
        await self.db.commit()

    async def registrar_selfie(self, token: str, conteudo: bytes, extensao: str) -> CredencialAcesso:
        """Recebe a selfie de quem não tem login (convidado ou cliente de locação)."""
        cred = await self.dados_do_link(token)

        destino = os.path.join(_DIR_UPLOADS, "acesso")
        os.makedirs(destino, exist_ok=True)
        # Nome com sufixo aleatório: a pasta é servida sem login, e
        # `RT000012.jpg` deixava enumerar o rosto de todo convidado.
        nome_arquivo = nome_de_foto(cred.id_dispositivo, extensao)
        with open(os.path.join(destino, nome_arquivo), "wb") as f:
            f.write(conteudo)
        apagar_foto_antiga(cred.foto_url, destino)

        cred.foto_url = f"/uploads/acesso/{nome_arquivo}"
        cred.foto_hash = hashlib.sha256(conteudo).hexdigest()
        cred.status = StatusCredencial.PENDENTE_ENVIO
        cred.erro = None

        # Espelha na origem, para o cadastro do convidado carregar a foto também.
        if cred.convidado_id:
            from app.models.convidado import Convidado
            conv = await self.db.get(Convidado, cred.convidado_id)
            if conv:
                conv.foto_url = cred.foto_url

        await self.db.commit()
        return cred

    # ── Janelas ──────────────────────────────────────────────────────────────

    async def sincronizar_booking(self, booking_id: int) -> int:
        """(Re)cria as janelas de acesso de uma reserva. Devolve quantas ficaram.

        Idempotente: pode ser chamada quantas vezes for, em qualquer ponto do
        ciclo de vida da reserva. É o único caminho para criar janela.
        """
        cfg = await Configuracao.get(self.db)
        if not cfg.acesso_ativo:
            return 0

        booking = (
            await self.db.execute(
                select(Booking)
                .where(Booking.id == booking_id)
                .options(
                    selectinload(Booking.jogador_responsavel),
                    selectinload(Booking.match)
                    .selectinload(Match.participantes),
                )
            )
        ).scalar_one_or_none()
        if booking is None:
            return 0

        # Cancelada perde o acesso; a reconciliação do agente tira do leitor.
        if booking.status == StatusReserva.CANCELADA:
            await self.revogar_booking(booking_id)
            return 0

        credenciais = await self._credenciais_da_reserva(booking)

        inicio = booking.data_hora_inicio - timedelta(minutes=cfg.acesso_minutos_antes)
        fim = booking.data_hora_fim + timedelta(minutes=cfg.acesso_minutos_depois)

        # Recriar é mais simples e mais seguro que casar janela a janela: os
        # participantes mudam (convidado trocado, dupla desfeita) e uma janela
        # órfã liberaria o portão para quem não joga mais.
        await self.db.execute(
            update(JanelaAcesso)
            .where(JanelaAcesso.booking_id == booking_id, JanelaAcesso.status == StatusJanela.ATIVA)
            .values(status=StatusJanela.CANCELADA)
        )

        for cred in credenciais:
            self.db.add(
                JanelaAcesso(
                    credencial_id=cred.id,
                    booking_id=booking_id,
                    inicio=inicio,
                    fim=fim,
                    status=StatusJanela.ATIVA,
                )
            )

        await self.db.commit()
        return len(credenciais)

    async def revogar_booking(self, booking_id: int) -> None:
        await self.db.execute(
            update(JanelaAcesso)
            .where(JanelaAcesso.booking_id == booking_id, JanelaAcesso.status == StatusJanela.ATIVA)
            .values(status=StatusJanela.CANCELADA)
        )
        await self.db.commit()

    async def _credenciais_da_reserva(self, booking: Booking) -> list[CredencialAcesso]:
        """Quem tem direito de entrar por causa desta reserva."""
        credenciais: list[CredencialAcesso] = []

        if booking.match is not None:
            # Ranking e jogo avulso: todo participante entra.
            for p in booking.match.participantes:
                if p.player_id:
                    jogador = await self.db.get(_Player(), p.player_id)
                    if jogador:
                        credenciais.append(await self.credencial_do_player(jogador))
                elif p.convidado_id:
                    from app.models.convidado import Convidado
                    conv = await self.db.get(Convidado, p.convidado_id)
                    if conv:
                        credenciais.append(await self.credencial_do_convidado(conv))
        elif booking.tipo == TipoReserva.LOCACAO_AVULSA:
            # Associado pode alugar avulso além da cota do ranking; nesse caso
            # ele entra pela credencial dele, não pela da reserva.
            if booking.jogador_responsavel is not None:
                credenciais.append(await self.credencial_do_player(booking.jogador_responsavel))
            else:
                credenciais.append(await self.credencial_da_locacao(booking))

        await self.db.flush()
        return credenciais

    # ── Estado desejado para o agente ────────────────────────────────────────

    async def estado_para_agente(self) -> dict:
        """Retrato completo do que os leitores devem conter.

        O agente compara com o que está nos equipamentos e corrige a diferença.
        Mandar o estado inteiro (e não um diff) é o que faz o agente se recuperar
        sozinho de qualquer dessincronia, inclusive de alguém ter mexido na tela
        do leitor.
        """
        cfg = await Configuracao.get(self.db)
        agora = datetime.now(timezone.utc)

        dispositivos = (
            await self.db.execute(
                select(DispositivoAcesso).where(DispositivoAcesso.ativo.is_(True))
            )
        ).scalars().all()

        janelas = (
            await self.db.execute(
                select(JanelaAcesso)
                .where(
                    JanelaAcesso.status == StatusJanela.ATIVA,
                    JanelaAcesso.fim >= agora - RETENCAO_JANELAS,
                    JanelaAcesso.inicio <= agora + HORIZONTE_JANELAS,
                )
                .options(selectinload(JanelaAcesso.credencial))
                .order_by(JanelaAcesso.inicio)
            )
        ).scalars().all()

        # Só vai para o leitor quem tem foto: sem selfie não há o que cadastrar.
        por_credencial: dict[int, list[JanelaAcesso]] = {}
        for j in janelas:
            if j.credencial.foto_hash:
                por_credencial.setdefault(j.credencial_id, []).append(j)

        credenciais = []
        for cred_id, suas in por_credencial.items():
            cred = suas[0].credencial
            credenciais.append({
                "id": cred.id,
                "id_dispositivo": cred.id_dispositivo,
                "nome": cred.nome,
                "foto_url": cred.foto_url,
                "foto_hash": cred.foto_hash,
                "janelas": [
                    {"inicio": j.inicio.isoformat(), "fim": j.fim.isoformat()}
                    for j in suas
                ],
            })

        from app.core.cripto import decifrar
        return {
            "gerado_em": agora.isoformat(),
            "acesso_ativo": cfg.acesso_ativo,
            "minutos_antes": cfg.acesso_minutos_antes,
            "minutos_depois": cfg.acesso_minutos_depois,
            "dispositivos": [
                {
                    "id": d.id,
                    "nome": d.nome,
                    "papel": d.papel.value,
                    "modelo": d.modelo,
                    "host": d.host,
                    "porta": d.porta,
                    "usuario": d.usuario,
                    "senha": decifrar(d.senha_cifrada),
                }
                for d in dispositivos
            ],
            "credenciais": credenciais,
        }

    # ── Eventos vindos dos leitores ──────────────────────────────────────────

    async def registrar_eventos(self, eventos: list[dict]) -> int:
        """Grava as passagens. Ignora repetidos pela chave externa."""
        if not eventos:
            return 0

        chaves = [e["chave_externa"] for e in eventos]
        ja_temos = set(
            (
                await self.db.execute(
                    select(EventoAcesso.chave_externa).where(EventoAcesso.chave_externa.in_(chaves))
                )
            ).scalars().all()
        )

        # Mapa id_dispositivo → credencial, para casar o evento com a pessoa.
        ids = {e.get("id_dispositivo") for e in eventos if e.get("id_dispositivo")}
        por_id_dispositivo = {}
        if ids:
            for cred in (
                await self.db.execute(
                    select(CredencialAcesso).where(CredencialAcesso.id_dispositivo.in_(ids))
                )
            ).scalars().all():
                por_id_dispositivo[cred.id_dispositivo] = cred

        gravados = 0
        for e in eventos:
            if e["chave_externa"] in ja_temos:
                continue
            # Um lote pode repetir a mesma chave; a constraint única pegaria o
            # segundo e derrubaria o relatório inteiro
            ja_temos.add(e["chave_externa"])
            cred = por_id_dispositivo.get(e.get("id_dispositivo") or "")
            momento = e["momento"]
            if isinstance(momento, str):
                momento = datetime.fromisoformat(momento)
            self.db.add(
                EventoAcesso(
                    dispositivo_id=e.get("dispositivo_id"),
                    credencial_id=cred.id if cred else None,
                    tipo=TipoEventoAcesso(e["tipo"]),
                    momento=momento,
                    nome_lido=(e.get("nome_lido") or "")[:150] or None,
                    motivo=(e.get("motivo") or "")[:200] or None,
                    chave_externa=e["chave_externa"],
                )
            )
            gravados += 1

        await self.db.commit()
        return gravados

    async def confirmar_sincronizacao(self, resultados: list[dict]) -> None:
        """O agente diz o que conseguiu (ou não) gravar em cada leitor."""
        for r in resultados:
            cred = await self.db.get(CredencialAcesso, r["credencial_id"])
            if cred is None:
                continue
            if r.get("ok"):
                cred.status = StatusCredencial.SINCRONIZADA
                cred.erro = None
                cred.sincronizada_em = datetime.now(timezone.utc)
            else:
                cred.status = StatusCredencial.ERRO
                cred.erro = (r.get("erro") or "")[:500]
        await self.db.commit()

    async def marcar_agente_visto(self, saude_dispositivos: list[dict] | None = None) -> None:
        """Batimento do agente, com o estado de cada leitor."""
        cfg = await Configuracao.get(self.db)
        cfg.acesso_agente_visto_em = datetime.now(timezone.utc)

        for d in saude_dispositivos or []:
            disp = await self.db.get(DispositivoAcesso, d.get("id"))
            if disp is None:
                continue
            if d.get("ok"):
                disp.ultimo_contato_em = datetime.now(timezone.utc)
                disp.ultimo_erro = None
            else:
                disp.ultimo_erro = (d.get("erro") or "")[:500]
        await self.db.commit()

    # ── Comandos pontuais ────────────────────────────────────────────────────

    async def enfileirar_comando(self, tipo: str, payload: dict) -> ComandoAcesso:
        cmd = ComandoAcesso(tipo=tipo, payload=payload)
        self.db.add(cmd)
        await self.db.commit()
        await self.db.refresh(cmd)
        return cmd

    async def comandos_pendentes(self) -> list[ComandoAcesso]:
        return list(
            (
                await self.db.execute(
                    select(ComandoAcesso)
                    .where(ComandoAcesso.status == StatusComando.PENDENTE)
                    .order_by(ComandoAcesso.id)
                    .limit(50)
                )
            ).scalars().all()
        )

    async def concluir_comando(self, comando_id: int, ok: bool, erro: str | None = None) -> None:
        cmd = await self.db.get(ComandoAcesso, comando_id)
        if cmd is None:
            return
        cmd.status = StatusComando.EXECUTADO if ok else StatusComando.ERRO
        cmd.erro = (erro or "")[:500] or None
        cmd.executado_em = datetime.now(timezone.utc)
        await self.db.commit()


# ── Auxiliares ───────────────────────────────────────────────────────────────

async def sincronizar_acesso_sem_erro(db: AsyncSession, booking_id: int) -> None:
    """Atualiza as janelas do portão de uma reserva sem deixar erro escapar.

    O jogo é o produto; o portão é acessório, e o agente reconcilia no ciclo
    seguinte de qualquer forma. Falha aqui vai para o log, não para o usuário.
    """
    try:
        await AcessoService(db).sincronizar_booking(booking_id)
    except Exception:  # noqa: BLE001 — acessório não derruba o principal
        logger.exception("Falha ao sincronizar acesso da reserva %s", booking_id)


def _id_dispositivo(credencial_id: int) -> str:
    """ID do usuário dentro do leitor: legível na tela do equipamento."""
    return f"RT{credencial_id:06d}"


def _hash_do_upload(foto_url: str) -> str | None:
    """sha256 do arquivo apontado por uma URL /uploads/... ou None se sumiu."""
    if not foto_url.startswith("/uploads/"):
        return None
    caminho = os.path.join(_DIR_UPLOADS, foto_url[len("/uploads/"):])
    try:
        with open(caminho, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _Player():
    """Import tardio: `Player` puxa metade dos modelos e criaria ciclo."""
    from app.models.player import Player
    return Player
