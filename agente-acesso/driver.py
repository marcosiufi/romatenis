"""Drivers dos leitores faciais.

Isola tudo que é específico do equipamento. O laço do agente (`agente.py`) fala
só com a interface `DriverLeitor` e não sabe se por trás está um leitor de
verdade ou o simulador.

Dois drivers:

- `DriverIntelbras` — fala com o leitor pela rede local via CGI/HTTP Digest.
- `DriverSimulado` — guarda tudo em memória. Permite testar o sistema inteiro
  (janelas, reconciliação, eventos, painel) antes de o hardware existir.

⚠️ ENDPOINTS AINDA NÃO CONFIRMADOS
A linha de controle de acesso da Intelbras é derivada da plataforma Dahua e usa
CGI sobre HTTP com autenticação Digest. Os caminhos em `_ROTAS` seguem essa
convenção, mas **não foram verificados contra a documentação oficial** — ela é
liberada pela Intelbras sob solicitação (ver o tutorial do chatbot em
`Acesso/Intelbras/`). Quando a documentação chegar, corrigir `_ROTAS` e os
formatos de payload é a única mudança necessária: nada fora deste arquivo
depende do dialeto do equipamento.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class ErroLeitor(RuntimeError):
    """Falha ao conversar com um leitor."""


class DriverLeitor(Protocol):
    """O que o agente precisa saber fazer com um leitor."""

    def testar(self) -> str: ...
    def listar_usuarios(self) -> dict[str, dict]: ...
    def gravar_usuario(self, id_dispositivo: str, nome: str, habilitado: bool) -> None: ...
    def gravar_face(self, id_dispositivo: str, foto: bytes) -> None: ...
    def definir_habilitado(self, id_dispositivo: str, habilitado: bool) -> None: ...
    def remover_usuario(self, id_dispositivo: str) -> None: ...
    def eventos_desde(self, desde: datetime) -> list[dict]: ...
    def abrir_porta(self) -> None: ...


# ── Leitor real ──────────────────────────────────────────────────────────────

# Caminhos CGI da plataforma. NÃO CONFIRMADOS — ver o aviso no topo do arquivo.
_ROTAS = {
    "tipo":            "/cgi-bin/magicBox.cgi?action=getDeviceType",
    "listar_usuarios": "/cgi-bin/AccessUser.cgi?action=list",
    "gravar_usuario":  "/cgi-bin/AccessUser.cgi?action=insertMulti",
    "editar_usuario":  "/cgi-bin/AccessUser.cgi?action=updateMulti",
    "remover_usuario": "/cgi-bin/AccessUser.cgi?action=removeMulti",
    "gravar_face":     "/cgi-bin/AccessFace.cgi?action=insertMulti",
    "buscar_eventos":  "/cgi-bin/recordFinder.cgi?action=find&name=AccessControlCardRec",
    "abrir_porta":     "/cgi-bin/accessControl.cgi?action=openDoor&channel=1&Type=Remote",
}


class DriverIntelbras:
    """Conversa com um SS 3531 / SS 7530 pela rede local.

    Autenticação Digest: a linha não aceita Basic. O timeout é curto de
    propósito — o agente roda em laço e um leitor mudo não pode travar o ciclo
    inteiro, senão o outro leitor também para de sincronizar.
    """

    def __init__(self, host: str, porta: int, usuario: str, senha: str, timeout: float = 8.0) -> None:
        self.base = f"http://{host}:{porta}"
        self._cliente = httpx.Client(
            auth=httpx.DigestAuth(usuario, senha),
            timeout=timeout,
        )

    def fechar(self) -> None:
        self._cliente.close()

    def _get(self, rota: str, **params) -> str:
        try:
            r = self._cliente.get(self.base + _ROTAS[rota], params=params or None)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise ErroLeitor(f"{rota}: {exc}") from exc

    def _post(self, rota: str, payload: dict) -> str:
        try:
            r = self._cliente.post(self.base + _ROTAS[rota], json=payload)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise ErroLeitor(f"{rota}: {exc}") from exc

    def testar(self) -> str:
        return self._get("tipo").strip()

    def listar_usuarios(self) -> dict[str, dict]:
        """Mapa id_dispositivo → {nome, habilitado}.

        Usado para a reconciliação: é como o agente descobre que alguém foi
        apagado na tela do equipamento ou que uma pessoa sobrou lá de um jogo
        antigo.
        """
        texto = self._get("listar_usuarios")
        return _parse_lista_usuarios(texto)

    def gravar_usuario(self, id_dispositivo: str, nome: str, habilitado: bool) -> None:
        self._post("gravar_usuario", {
            "UserList": [{
                "UserID": id_dispositivo,
                "UserName": nome,
                # Sem cartão nem senha: o acesso é só facial.
                "UserType": 0,
                "Authority": 2,
                "Doors": [0],
                "ValidDateStart": "2000-01-01 00:00:00",
                "ValidDateEnd": "2099-12-31 23:59:59",
                "Enable": bool(habilitado),
            }]
        })

    def gravar_face(self, id_dispositivo: str, foto: bytes) -> None:
        self._post("gravar_face", {
            "FaceList": [{
                "UserID": id_dispositivo,
                "PhotoData": [base64.b64encode(foto).decode("ascii")],
            }]
        })

    def definir_habilitado(self, id_dispositivo: str, habilitado: bool) -> None:
        """Liga/desliga a pessoa no leitor.

        É assim que a janela de horário é aplicada. O equipamento tem um período
        de validade por usuário, mas ele é um intervalo só — e uma pessoa pode
        ter vários jogos na semana. Ligar e desligar no relógio do agente cobre
        os dois casos com uma regra só.
        """
        self._post("editar_usuario", {
            "UserList": [{"UserID": id_dispositivo, "Enable": bool(habilitado)}]
        })

    def remover_usuario(self, id_dispositivo: str) -> None:
        self._post("remover_usuario", {"UserIDList": [id_dispositivo]})

    def eventos_desde(self, desde: datetime) -> list[dict]:
        texto = self._get(
            "buscar_eventos",
            StartTime=desde.strftime("%Y-%m-%d %H:%M:%S"),
            EndTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return _parse_eventos(texto)

    def abrir_porta(self) -> None:
        self._get("abrir_porta")


def _parse_lista_usuarios(texto: str) -> dict[str, dict]:
    """Lê a resposta `chave=valor` da plataforma.

    O formato é `records[N].Campo=valor`, uma linha por campo.
    """
    usuarios: dict[int, dict] = {}
    for linha in texto.splitlines():
        if "=" not in linha or not linha.startswith("records["):
            continue
        chave, valor = linha.split("=", 1)
        try:
            indice = int(chave[chave.index("[") + 1: chave.index("]")])
        except (ValueError, IndexError):
            continue
        campo = chave.rsplit(".", 1)[-1]
        usuarios.setdefault(indice, {})[campo] = valor.strip()

    saida: dict[str, dict] = {}
    for dados in usuarios.values():
        uid = dados.get("UserID")
        if uid:
            saida[uid] = {
                "nome": dados.get("UserName", ""),
                "habilitado": dados.get("Enable", "true").lower() != "false",
            }
    return saida


def _parse_eventos(texto: str) -> list[dict]:
    """Converte os registros de passagem no formato que o servidor espera."""
    registros: dict[int, dict] = {}
    for linha in texto.splitlines():
        if "=" not in linha or not linha.startswith("records["):
            continue
        chave, valor = linha.split("=", 1)
        try:
            indice = int(chave[chave.index("[") + 1: chave.index("]")])
        except (ValueError, IndexError):
            continue
        registros.setdefault(indice, {})[chave.rsplit(".", 1)[-1]] = valor.strip()

    eventos = []
    for dados in registros.values():
        momento = dados.get("CreateTime") or dados.get("Time")
        if not momento:
            continue
        eventos.append({
            "id_dispositivo": dados.get("UserID") or None,
            "momento": momento,
            "liberado": (dados.get("Status", "1") == "1"),
            "nome_lido": dados.get("CardName") or dados.get("UserName") or None,
            "motivo": dados.get("ErrorCode") or None,
            "id_registro": dados.get("RecNo") or momento,
        })
    return eventos


# ── Simulador ────────────────────────────────────────────────────────────────

class DriverSimulado:
    """Leitor de mentira, em memória.

    Existe para o sistema poder ser testado inteiro antes do hardware chegar e
    antes de a documentação da API sair: janelas, reconciliação, eventos e
    painel funcionam de verdade contra ele.
    """

    def __init__(self, nome: str = "simulado") -> None:
        self.nome = nome
        self.usuarios: dict[str, dict] = {}
        self.faces: dict[str, int] = {}
        self.eventos: list[dict] = []
        self.aberturas = 0

    def testar(self) -> str:
        return f"simulador:{self.nome}"

    def listar_usuarios(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self.usuarios.items()}

    def gravar_usuario(self, id_dispositivo: str, nome: str, habilitado: bool) -> None:
        self.usuarios[id_dispositivo] = {"nome": nome, "habilitado": habilitado}

    def gravar_face(self, id_dispositivo: str, foto: bytes) -> None:
        if id_dispositivo not in self.usuarios:
            raise ErroLeitor(f"usuário {id_dispositivo} não existe no leitor")
        self.faces[id_dispositivo] = len(foto)

    def definir_habilitado(self, id_dispositivo: str, habilitado: bool) -> None:
        if id_dispositivo not in self.usuarios:
            raise ErroLeitor(f"usuário {id_dispositivo} não existe no leitor")
        self.usuarios[id_dispositivo]["habilitado"] = habilitado

    def remover_usuario(self, id_dispositivo: str) -> None:
        self.usuarios.pop(id_dispositivo, None)
        self.faces.pop(id_dispositivo, None)

    def eventos_desde(self, desde: datetime) -> list[dict]:
        pendentes, self.eventos = self.eventos, []
        return pendentes

    def abrir_porta(self) -> None:
        self.aberturas += 1

    # Usado pelos testes para simular alguém passando pelo leitor.
    def simular_passagem(self, id_dispositivo: str, liberado: bool = True) -> None:
        agora = datetime.now(timezone.utc)
        self.eventos.append({
            "id_dispositivo": id_dispositivo,
            "momento": agora.strftime("%Y-%m-%d %H:%M:%S"),
            "liberado": liberado,
            "nome_lido": self.usuarios.get(id_dispositivo, {}).get("nome"),
            "motivo": None if liberado else "face não reconhecida",
            "id_registro": f"{self.nome}-{len(self.eventos)}-{agora.timestamp()}",
        })
