"""Drivers dos leitores faciais.

Isola tudo que é específico do equipamento. O laço do agente (`agente.py`) fala
só com a interface `DriverLeitor` e não sabe se por trás está um leitor de
verdade ou o simulador.

Endpoints conferidos contra a coleção Postman oficial da Intelbras
("Controle de Acesso - Bio-T") e o Portal de Integração da Linha de Faciais, que
confirma o SS 3531 MF como suportado. Autenticação **Digest** (RFC 2617); a
resposta vem como `chave=valor` multilinha, JSON, ou a palavra "OK".

A coleção convive com duas gerações de API. Onde há escolha, este driver usa a
**V2** (`AccessUser.cgi`, `AccessFace.cgi`), que trabalha com `UserID` como
identificador natural em vez do `recno` interno do equipamento — o `recno` muda
quando o registro é reescrito, e amarrar nossa credencial a ele seria frágil.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

# Fora de qualquer janela: validade num intervalo já vencido. É assim que a
# pessoa fica bloqueada sem precisar apagá-la do leitor — apagar custaria
# reenviar a foto na próxima reserva.
VALIDADE_BLOQUEADO = ("2000-01-01 00:00:00", "2000-01-01 00:00:01")

_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


class ErroLeitor(RuntimeError):
    """Falha ao conversar com um leitor."""


class DriverLeitor(Protocol):
    """O que o agente precisa saber fazer com um leitor."""

    def testar(self) -> str: ...
    def listar_usuarios(self, ids: list[str]) -> dict[str, dict]: ...
    def listar_todos_ids(self) -> set[str]: ...
    def gravar_usuario(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None: ...
    def atualizar_validade(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None: ...
    def gravar_face(self, uid: str, foto: bytes) -> None: ...
    def remover_usuario(self, uid: str) -> None: ...
    def eventos_desde(self, desde: datetime) -> list[dict]: ...
    def abrir_porta(self) -> None: ...
    def configurar_ntp(self, servidor: str) -> None: ...


# ── Leitor real ──────────────────────────────────────────────────────────────

class DriverIntelbras:
    """Conversa com um SS 3531 MF / SS 7530 pela rede local.

    O timeout é curto de propósito: o agente roda em laço e um leitor mudo não
    pode travar o ciclo inteiro, senão o outro leitor também para de sincronizar.
    """

    def __init__(self, host: str, porta: int, usuario: str, senha: str, timeout: float = 8.0) -> None:
        self.base = f"http://{host}:{porta}"
        self._cliente = httpx.Client(auth=httpx.DigestAuth(usuario, senha), timeout=timeout)

    def fechar(self) -> None:
        self._cliente.close()

    # ── Transporte ───────────────────────────────────────────────────────────

    def _get(self, caminho: str) -> str:
        try:
            r = self._cliente.get(self.base + caminho)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise ErroLeitor(f"GET {caminho.split('?')[0]}: {exc}") from exc

    def _post(self, caminho: str, payload: dict) -> str:
        try:
            r = self._cliente.post(self.base + caminho, json=payload)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise ErroLeitor(f"POST {caminho.split('?')[0]}: {exc}") from exc

    # ── Dispositivo ──────────────────────────────────────────────────────────

    def testar(self) -> str:
        return self._get("/cgi-bin/magicBox.cgi?action=getSoftwareVersion").strip()

    def configurar_ntp(self, servidor: str = "a.ntp.br") -> None:
        """Aponta o relógio do leitor para o NTP.

        O horário das passagens vem do equipamento: relógio errado embaralha
        quem entrou e quem saiu. Fazer isso pelo agente evita depender de
        alguém lembrar de configurar na tela.
        """
        self._get(
            f"/cgi-bin/configManager.cgi?action=setConfig"
            f"&NTP.Address={servidor}&NTP.Enable=true"
        )

    # ── Usuários ─────────────────────────────────────────────────────────────

    @staticmethod
    def _corpo_usuario(uid: str, nome: str, valido_de: str, valido_ate: str) -> dict:
        return {
            "UserID": uid,
            "UserName": nome[:32],
            "UserType": 0,          # 0 = usuário comum
            "UserStatus": 0,        # 0 = normal
            "Authority": 2,         # 2 = usuário; 1 seria administrador do leitor
            "Doors": [0],           # única porta do equipamento
            "TimeSections": [255],  # 255 = qualquer horário dentro da validade
            "SpecialDaysSchedule": [255],
            # A janela do jogo vira a validade do usuário: quem impõe o horário
            # é o próprio leitor, não o agente. Se o agente cair no meio do
            # jogo, o acesso ainda fecha sozinho no fim da janela.
            "ValidFrom": valido_de,
            "ValidTo": valido_ate,
        }

    def gravar_usuario(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None:
        self._post(
            "/cgi-bin/AccessUser.cgi?action=insertMulti",
            {"UserList": [self._corpo_usuario(uid, nome, valido_de, valido_ate)]},
        )

    def atualizar_validade(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None:
        # updateMulti espera o registro completo, não só os campos alterados —
        # por isso o nome vem junto, senão seria sobrescrito.
        self._post(
            "/cgi-bin/AccessUser.cgi?action=updateMulti",
            {"UserList": [self._corpo_usuario(uid, nome, valido_de, valido_ate)]},
        )

    def listar_usuarios(self, ids: list[str]) -> dict[str, dict]:
        """Estado atual dos usuários que nos interessam.

        Consulta por `UserIDList[N]`, em lotes: uma URL com centenas de
        parâmetros estoura o limite de linha do servidor embarcado.
        """
        encontrados: dict[str, dict] = {}
        for i in range(0, len(ids), 40):
            lote = ids[i:i + 40]
            params = "".join(f"&UserIDList[{n}]={uid}" for n, uid in enumerate(lote))
            texto = self._get(f"/cgi-bin/AccessUser.cgi?action=list{params}")
            encontrados.update(_ler_usuarios(texto))
        return encontrados

    def listar_todos_ids(self) -> set[str]:
        """Todo UserID gravado no leitor — usado para achar sobras nossas."""
        texto = self._get(
            "/cgi-bin/recordFinder.cgi?action=find&name=AccessControlCard&condition.count=1024"
        )
        return {d["UserID"] for d in _ler_registros(texto).values() if d.get("UserID")}

    def remover_usuario(self, uid: str) -> None:
        # removeMulti é GET com os ids na query, não POST com corpo.
        self._get(f"/cgi-bin/AccessUser.cgi?action=removeMulti&UserIDList[0]={uid}")

    # ── Face ─────────────────────────────────────────────────────────────────

    def gravar_face(self, uid: str, foto: bytes) -> None:
        self._post(
            "/cgi-bin/AccessFace.cgi?action=insertMulti",
            {"FaceList": [{"UserID": uid, "PhotoData": [base64.b64encode(foto).decode("ascii")]}]},
        )

    # ── Eventos ──────────────────────────────────────────────────────────────

    def eventos_desde(self, desde: datetime) -> list[dict]:
        # StartTime é epoch em segundos, não data formatada.
        inicio = int(desde.timestamp())
        texto = self._get(
            f"/cgi-bin/recordFinder.cgi?action=find&name=AccessControlCardRec&StartTime={inicio}"
        )
        return _ler_eventos(texto)

    # ── Porta ────────────────────────────────────────────────────────────────

    def abrir_porta(self) -> None:
        self._get("/cgi-bin/accessControl.cgi?action=openDoor&channel=1&Type=Remote")


# ── Leitura das respostas ────────────────────────────────────────────────────

def _ler_registros(texto: str) -> dict[int, dict]:
    """Converte a resposta `records[N].Campo=valor` num dicionário por índice."""
    registros: dict[int, dict] = {}
    for linha in texto.splitlines():
        if "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        if "[" not in chave or "]" not in chave:
            continue
        try:
            indice = int(chave[chave.index("[") + 1: chave.index("]")])
        except ValueError:
            continue
        registros.setdefault(indice, {})[chave.rsplit(".", 1)[-1]] = valor.strip()
    return registros


def _ler_usuarios(texto: str) -> dict[str, dict]:
    """Usuários da resposta do `AccessUser.cgi?action=list`.

    A V2 costuma responder JSON, mas o portal documenta que a mesma API pode
    devolver `chave=valor`. Tenta os dois: assumir um formato só quebraria numa
    troca de firmware.
    """
    saida: dict[str, dict] = {}

    try:
        dados = json.loads(texto)
    except ValueError:
        dados = None

    if isinstance(dados, dict):
        for u in dados.get("UserList", []) or []:
            uid = str(u.get("UserID", "")).strip()
            if uid:
                saida[uid] = {
                    "nome": u.get("UserName", ""),
                    "valido_de": u.get("ValidFrom", ""),
                    "valido_ate": u.get("ValidTo", ""),
                }
        return saida

    for d in _ler_registros(texto).values():
        uid = d.get("UserID")
        if uid:
            saida[uid] = {
                "nome": d.get("UserName", ""),
                "valido_de": d.get("ValidFrom", ""),
                "valido_ate": d.get("ValidTo", ""),
            }
    return saida


def _ler_eventos(texto: str) -> list[dict]:
    """Passagens da resposta do `recordFinder.cgi`."""
    eventos = []
    for indice, d in sorted(_ler_registros(texto).items()):
        momento = d.get("CreateTime") or d.get("Time")
        if not momento:
            continue
        # Status 1 = liberado. Qualquer outro valor é recusa.
        liberado = d.get("Status", "1") == "1"
        eventos.append({
            "id_dispositivo": d.get("UserID") or None,
            "momento": momento,
            "liberado": liberado,
            "nome_lido": d.get("CardName") or d.get("UserName") or None,
            "motivo": None if liberado else (d.get("ErrorCode") or "acesso negado"),
            # RecNo é o número do registro no leitor; serve de chave estável.
            "id_registro": d.get("RecNo") or f"{indice}-{momento}",
        })
    return eventos


def formatar_data(dt: datetime) -> str:
    """Datas vão ao leitor em hora local, sem fuso — é o que ele entende."""
    return dt.astimezone().strftime(_FORMATO_DATA)


# ── Simulador ────────────────────────────────────────────────────────────────

class DriverSimulado:
    """Leitor de mentira, em memória.

    Permite testar o sistema inteiro — janelas, reconciliação, eventos, painel —
    sem hardware. Reproduz a regra que importa: a validade decide quem passa.
    """

    def __init__(self, nome: str = "simulado") -> None:
        self.nome = nome
        self.usuarios: dict[str, dict] = {}
        self.faces: dict[str, int] = {}
        self.eventos: list[dict] = []
        self.aberturas = 0
        self.ntp: str | None = None

    def testar(self) -> str:
        return f"simulador:{self.nome}"

    def configurar_ntp(self, servidor: str = "a.ntp.br") -> None:
        self.ntp = servidor

    def listar_usuarios(self, ids: list[str]) -> dict[str, dict]:
        return {uid: dict(self.usuarios[uid]) for uid in ids if uid in self.usuarios}

    def listar_todos_ids(self) -> set[str]:
        return set(self.usuarios)

    def gravar_usuario(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None:
        self.usuarios[uid] = {"nome": nome, "valido_de": valido_de, "valido_ate": valido_ate}

    def atualizar_validade(self, uid: str, nome: str, valido_de: str, valido_ate: str) -> None:
        if uid not in self.usuarios:
            raise ErroLeitor(f"usuário {uid} não existe no leitor")
        self.usuarios[uid].update(nome=nome, valido_de=valido_de, valido_ate=valido_ate)

    def gravar_face(self, uid: str, foto: bytes) -> None:
        if uid not in self.usuarios:
            raise ErroLeitor(f"usuário {uid} não existe no leitor")
        self.faces[uid] = len(foto)

    def remover_usuario(self, uid: str) -> None:
        self.usuarios.pop(uid, None)
        self.faces.pop(uid, None)

    def eventos_desde(self, desde: datetime) -> list[dict]:
        pendentes, self.eventos = self.eventos, []
        return pendentes

    def abrir_porta(self) -> None:
        self.aberturas += 1

    # ── Auxiliares de teste ──────────────────────────────────────────────────

    def liberado_agora(self, uid: str, agora: datetime | None = None) -> bool:
        """Aplica a validade como o equipamento aplicaria."""
        u = self.usuarios.get(uid)
        if not u or not u.get("valido_de"):
            return False
        agora = agora or datetime.now()
        de = datetime.strptime(u["valido_de"], _FORMATO_DATA)
        ate = datetime.strptime(u["valido_ate"], _FORMATO_DATA)
        return de <= agora.astimezone().replace(tzinfo=None) <= ate

    def simular_passagem(self, uid: str, liberado: bool | None = None) -> None:
        agora = datetime.now(timezone.utc)
        if liberado is None:
            liberado = self.liberado_agora(uid)
        self.eventos.append({
            "id_dispositivo": uid,
            "momento": agora.astimezone().strftime(_FORMATO_DATA),
            "liberado": liberado,
            "nome_lido": self.usuarios.get(uid, {}).get("nome"),
            "motivo": None if liberado else "acesso negado",
            "id_registro": f"{self.nome}-{len(self.eventos)}-{agora.timestamp()}",
        })
