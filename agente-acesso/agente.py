"""Agente de controle de acesso da Roma Tênis.

Roda num mini-PC na quadra, na mesma rede dos leitores faciais. É a ponte entre
o servidor (que está na nuvem e não alcança 192.168.x.x) e os equipamentos.

Ciclo, a cada `INTERVALO_SEGUNDOS`:

1. busca o estado desejado no servidor (quem pode entrar, em que janelas);
2. reconcilia cada leitor com esse estado — cadastra quem falta, remove quem
   sobrou, liga e desliga conforme o relógio;
3. recolhe as passagens registradas pelos leitores;
4. devolve tudo ao servidor num relatório só;
5. executa comandos pontuais (abrir o portão pelo painel).

Duas decisões que valem entender:

**O servidor manda o estado inteiro, não um diff.** Custa alguns KB por ciclo e
paga com robustez: se o agente ficar horas offline, se alguém apagar um usuário
na tela do leitor, ou se um leitor for trocado, o ciclo seguinte conserta
sozinho. Não existe estado que só o agente saiba.

**Quem impõe o horário é o leitor, não o agente.** Cada usuário tem uma validade
(`ValidFrom`/`ValidTo`) e o equipamento a respeita sozinho. O agente só mantém
essa validade apontando para a janela que importa — a que está acontecendo ou a
próxima. Assim, se o agente cair no meio do jogo, o acesso ainda fecha na hora
certa; e como o associado pode ter vários jogos na semana, o agente vai
avançando a validade de uma janela para a seguinte.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from driver import (
    VALIDADE_BLOQUEADO,
    DriverIntelbras,
    DriverSimulado,
    ErroLeitor,
    formatar_data,
)

logger = logging.getLogger("agente")

INTERVALO_SEGUNDOS = 20
# Quanto tempo para trás buscar passagens quando o agente sobe sem estado
# anterior. Cobre uma parada curta sem varrer o histórico inteiro do leitor.
JANELA_EVENTOS_INICIAL = timedelta(hours=6)
ARQUIVO_ESTADO = Path(__file__).with_name("estado-local.json")


class Agente:
    def __init__(self, base_url: str, token: str, simulado: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.simulado = simulado
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        self.drivers: dict[int, object] = {}
        self.local = self._carregar_estado()

    # ── Estado local ─────────────────────────────────────────────────────────

    def _carregar_estado(self) -> dict:
        """Lê o que o agente sabia antes de reiniciar.

        Guarda o hash da foto já enviada a cada leitor e o cursor de eventos —
        sem isso o agente reenviaria todas as fotos e reprocessaria passagens
        antigas a cada restart.
        """
        try:
            return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"fotos": {}, "cursor_eventos": {}}

    def _salvar_estado(self) -> None:
        try:
            ARQUIVO_ESTADO.write_text(
                json.dumps(self.local, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            logger.warning("não consegui gravar %s", ARQUIVO_ESTADO)

    # ── Servidor ─────────────────────────────────────────────────────────────

    def buscar_estado(self) -> dict:
        r = self.http.get(f"{self.base_url}/api/v1/acesso/agente/estado")
        r.raise_for_status()
        return r.json()

    def enviar_relatorio(self, corpo: dict) -> None:
        r = self.http.post(f"{self.base_url}/api/v1/acesso/agente/relatorio", json=corpo)
        r.raise_for_status()

    def concluir_comando(self, comando_id: int, ok: bool, erro: str | None = None) -> None:
        self.http.post(
            f"{self.base_url}/api/v1/acesso/agente/comandos/{comando_id}",
            json={"comando_id": comando_id, "ok": ok, "erro": erro},
        )

    def baixar_foto(self, foto_url: str) -> bytes:
        r = self.http.get(f"{self.base_url}{foto_url}")
        r.raise_for_status()
        return r.content

    # ── Leitores ─────────────────────────────────────────────────────────────

    def driver_de(self, disp: dict):
        """Reaproveita a conexão entre ciclos; recria se a configuração mudou."""
        chave = disp["id"]
        assinatura = (disp["host"], disp["porta"], disp["usuario"], disp.get("senha", ""))
        anterior = getattr(self, "_assinaturas", {}).get(chave)
        if chave in self.drivers and anterior == assinatura:
            return self.drivers[chave]

        if not hasattr(self, "_assinaturas"):
            self._assinaturas = {}
        antigo = self.drivers.pop(chave, None)
        if antigo is not None and hasattr(antigo, "fechar"):
            antigo.fechar()

        if self.simulado:
            drv = DriverSimulado(nome=disp["nome"])
        else:
            drv = DriverIntelbras(
                host=disp["host"], porta=disp["porta"],
                usuario=disp["usuario"], senha=disp.get("senha", ""),
            )
        self.drivers[chave] = drv
        self._assinaturas[chave] = assinatura
        return drv

    # ── Reconciliação ────────────────────────────────────────────────────────

    @staticmethod
    def _janela_relevante(credencial: dict, agora: datetime) -> tuple[str, str]:
        """Validade que a pessoa deve ter no leitor, em hora local.

        A janela em curso, se houver; senão a próxima que vier. O equipamento
        guarda um intervalo só por usuário, então o agente escolhe qual dos
        jogos da semana está valendo e vai avançando conforme eles terminam.
        Sem janela nenhuma, devolve um intervalo já vencido — a pessoa segue
        cadastrada (a foto não precisa subir de novo) mas não passa.
        """
        emcurso, futuras = None, []
        for j in credencial["janelas"]:
            inicio = datetime.fromisoformat(j["inicio"])
            fim = datetime.fromisoformat(j["fim"])
            if inicio <= agora <= fim:
                # Entre janelas sobrepostas vale a que termina depois.
                if emcurso is None or fim > emcurso[1]:
                    emcurso = (inicio, fim)
            elif inicio > agora:
                futuras.append((inicio, fim))

        escolhida = emcurso or (min(futuras) if futuras else None)
        if escolhida is None:
            return VALIDADE_BLOQUEADO
        return formatar_data(escolhida[0]), formatar_data(escolhida[1])

    def reconciliar(self, disp: dict, credenciais: list[dict], agora: datetime) -> tuple[list[dict], str | None]:
        """Deixa um leitor igual ao estado desejado.

        Devolve (resultados por credencial, erro do leitor). Erro de uma pessoa
        não interrompe as outras: um rosto que o equipamento recusa não pode
        impedir o resto da quadra de entrar.
        """
        drv = self.driver_de(disp)
        ids = [c["id_dispositivo"] for c in credenciais]
        try:
            drv.testar()
            self._ajustar_relogio(disp, drv)
            no_leitor = drv.listar_usuarios(ids) if ids else {}
        except ErroLeitor as exc:
            return [], str(exc)
        except Exception as exc:  # noqa: BLE001 — leitor fora do ar não derruba o agente
            return [], f"{type(exc).__name__}: {exc}"

        fotos_enviadas = self.local.setdefault("fotos", {}).setdefault(str(disp["id"]), {})
        resultados: list[dict] = []

        for cred in credenciais:
            uid = cred["id_dispositivo"]
            valido_de, valido_ate = self._janela_relevante(cred, agora)
            try:
                atual = no_leitor.get(uid)
                if atual is None:
                    drv.gravar_usuario(uid, cred["nome"], valido_de, valido_ate)
                    # Usuário novo: a foto tem de subir, mesmo que já estivesse
                    # no cache de um cadastro anterior que foi apagado.
                    fotos_enviadas.pop(uid, None)
                elif (atual.get("valido_de"), atual.get("valido_ate")) != (valido_de, valido_ate):
                    drv.atualizar_validade(uid, cred["nome"], valido_de, valido_ate)

                # A foto só vai quando muda: é o payload pesado do ciclo.
                if fotos_enviadas.get(uid) != cred["foto_hash"]:
                    drv.gravar_face(uid, self.baixar_foto(cred["foto_url"]))
                    fotos_enviadas[uid] = cred["foto_hash"]

                resultados.append({"credencial_id": cred["id"], "ok": True})
            except Exception as exc:  # noqa: BLE001 — por pessoa, não por leitor
                logger.warning("credencial %s no leitor %s: %s", uid, disp["nome"], exc)
                resultados.append({
                    "credencial_id": cred["id"], "ok": False,
                    "erro": f"{disp['nome']}: {exc}",
                })

        self._limpar_sobras(disp, drv, set(ids), fotos_enviadas)
        return resultados, None

    def _limpar_sobras(self, disp: dict, drv, esperados: set[str], fotos_enviadas: dict) -> None:
        """Apaga do leitor quem o servidor não conhece mais.

        Só mexe no que é nosso (prefixo RT): um usuário cadastrado à mão na tela
        do equipamento — o zelador, um técnico — não pode ser apagado por nós.
        """
        try:
            no_leitor = drv.listar_todos_ids()
        except Exception as exc:  # noqa: BLE001 — limpeza é acessória
            logger.warning("não listei os usuários de %s: %s", disp["nome"], exc)
            return

        for uid in no_leitor:
            if uid.startswith("RT") and uid not in esperados:
                try:
                    drv.remover_usuario(uid)
                    fotos_enviadas.pop(uid, None)
                    logger.info("removido do leitor %s: %s", disp["nome"], uid)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("não removi %s de %s: %s", uid, disp["nome"], exc)

    def _ajustar_relogio(self, disp: dict, drv) -> None:
        """Aponta o NTP do leitor, uma vez por execução do agente.

        O horário das passagens vem do equipamento: relógio errado embaralha
        quem entrou e quem saiu. Fazer aqui evita depender de alguém lembrar de
        configurar na tela de cada leitor.
        """
        if not hasattr(self, "_ntp_ajustado"):
            self._ntp_ajustado = set()
        if disp["id"] in self._ntp_ajustado:
            return
        try:
            drv.configurar_ntp("a.ntp.br")
            self._ntp_ajustado.add(disp["id"])
        except Exception as exc:  # noqa: BLE001 — não impede o ciclo
            logger.warning("NTP do leitor %s: %s", disp["nome"], exc)

    def coletar_eventos(self, disp: dict) -> list[dict]:
        """Passagens registradas desde a última coleta deste leitor."""
        drv = self.driver_de(disp)
        cursores = self.local.setdefault("cursor_eventos", {})
        chave = str(disp["id"])
        desde = (
            datetime.fromisoformat(cursores[chave])
            if chave in cursores
            else datetime.now(timezone.utc) - JANELA_EVENTOS_INICIAL
        )
        try:
            brutos = drv.eventos_desde(desde)
        except Exception as exc:  # noqa: BLE001
            logger.warning("eventos do leitor %s: %s", disp["nome"], exc)
            return []

        entrada = disp["papel"] == "entrada"
        eventos = []
        for e in brutos:
            eventos.append({
                # A chave junta leitor e registro: é o que impede o servidor de
                # duplicar quando um lote é reenviado por falha de rede.
                "chave_externa": f"{disp['id']}:{e['id_registro']}"[:120],
                "tipo": ("entrada" if entrada else "saida") if e["liberado"] else "negado",
                "momento": _para_iso(e["momento"]),
                "id_dispositivo": e.get("id_dispositivo"),
                "dispositivo_id": disp["id"],
                "nome_lido": e.get("nome_lido"),
                "motivo": e.get("motivo"),
            })
        cursores[chave] = datetime.now(timezone.utc).isoformat()
        return eventos

    def executar_comandos(self, comandos: list[dict], dispositivos: list[dict]) -> None:
        por_id = {d["id"]: d for d in dispositivos}
        for cmd in comandos:
            try:
                if cmd["tipo"] == "abrir_porta":
                    disp = por_id.get(cmd["payload"].get("dispositivo_id"))
                    if disp is None:
                        raise ErroLeitor("leitor não está ativo na configuração")
                    self.driver_de(disp).abrir_porta()
                    logger.info("portão aberto pelo painel: %s", disp["nome"])
                else:
                    raise ErroLeitor(f"comando desconhecido: {cmd['tipo']}")
                self.concluir_comando(cmd["id"], True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("comando %s falhou: %s", cmd["id"], exc)
                self.concluir_comando(cmd["id"], False, str(exc))

    # ── Ciclo ────────────────────────────────────────────────────────────────

    def ciclo(self) -> None:
        estado = self.buscar_estado()
        agora = datetime.now(timezone.utc)

        if not estado.get("acesso_ativo"):
            logger.info("controle de acesso desligado no painel; nada a fazer")
            self.enviar_relatorio({"dispositivos": [], "credenciais": [], "eventos": []})
            return

        dispositivos = estado.get("dispositivos", [])
        credenciais = estado.get("credenciais", [])
        if not dispositivos:
            logger.warning("nenhum leitor cadastrado no painel")
            return

        saude, resultados, eventos = [], {}, []
        for disp in dispositivos:
            parciais, erro = self.reconciliar(disp, credenciais, agora)
            saude.append({"id": disp["id"], "ok": erro is None, "erro": erro})
            if erro:
                logger.warning("leitor %s indisponível: %s", disp["nome"], erro)
                continue
            # Uma credencial só é dada como sincronizada se TODOS os leitores
            # aceitaram: entrar e não conseguir sair seria pior que não entrar.
            for r in parciais:
                anterior = resultados.get(r["credencial_id"])
                if anterior is None or (anterior["ok"] and not r["ok"]):
                    resultados[r["credencial_id"]] = r
            eventos.extend(self.coletar_eventos(disp))

        self.enviar_relatorio({
            "dispositivos": saude,
            "credenciais": list(resultados.values()),
            "eventos": eventos,
        })
        self.executar_comandos(estado.get("comandos", []), dispositivos)
        self._salvar_estado()

        logger.info(
            "ciclo ok — %d leitor(es), %d pessoa(s), %d evento(s)",
            len(dispositivos), len(credenciais), len(eventos),
        )

    def rodar(self) -> None:
        logger.info("agente iniciado (%s)", "SIMULADO" if self.simulado else "leitores reais")
        while True:
            try:
                self.ciclo()
            except httpx.HTTPStatusError as exc:
                logger.error("servidor respondeu %s", exc.response.status_code)
            except httpx.HTTPError as exc:
                # Sem internet o agente não trava: os leitores seguem com a
                # última lista sincronizada e quem tem jogo agora continua entrando.
                logger.error("sem contato com o servidor: %s", exc)
            except Exception:  # noqa: BLE001 — o laço não pode morrer
                logger.exception("erro inesperado no ciclo")
            time.sleep(INTERVALO_SEGUNDOS)


def _para_iso(momento: str) -> str:
    """Converte o horário do leitor para ISO com fuso.

    Os equipamentos devolvem hora local sem fuso. Assume-se que estão no mesmo
    fuso da quadra — por isso o README manda apontar o NTP dos dois leitores.
    """
    try:
        dt = datetime.strptime(momento, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(momento).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
    return dt.astimezone().isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description="Agente de controle de acesso — Roma Tênis")
    p.add_argument("--url", default=os.getenv("ROMA_URL", "https://romatenis.com.br"))
    p.add_argument("--token", default=os.getenv("ROMA_TOKEN", ""))
    p.add_argument("--simulado", action="store_true", default=bool(os.getenv("ROMA_SIMULADO")))
    p.add_argument("--uma-vez", action="store_true", help="roda um ciclo só e sai")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%d/%m %H:%M:%S",
    )

    if not args.token:
        print("Falta o token do agente. Gere no painel (Acesso) e passe em "
              "--token ou na variável ROMA_TOKEN.", file=sys.stderr)
        return 2

    agente = Agente(args.url, args.token, simulado=args.simulado)
    if args.uma_vez:
        agente.ciclo()
        return 0
    agente.rodar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
