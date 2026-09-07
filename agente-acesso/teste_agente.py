"""Testes do agente contra os leitores simulados.

Rodam sem servidor e sem hardware: o servidor é substituído por um dublê e os
leitores pelo `DriverSimulado`. É o que permite verificar a parte difícil — a
reconciliação e a janela de horário — antes de o equipamento existir.

    python teste_agente.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from agente import Agente
from driver import DriverSimulado


class HttpDuble:
    """Responde no lugar do servidor e guarda o que o agente enviou."""

    def __init__(self) -> None:
        self.relatorios: list[dict] = []
        self.comandos_concluidos: list[tuple[int, bool]] = []

    def get(self, url, **kwargs):
        raise AssertionError(f"GET inesperado: {url}")

    def post(self, url, json=None, **kwargs):
        raise AssertionError(f"POST inesperado: {url}")


def _agente() -> Agente:
    ag = Agente("http://servidor-de-teste", "token-de-teste", simulado=True)
    ag.http = HttpDuble()
    ag.local = {"fotos": {}, "cursor_eventos": {}}
    ag._salvar_estado = lambda: None            # não escreve em disco no teste
    ag.baixar_foto = lambda url: b"foto-falsa"  # não busca no servidor
    return ag


def _credencial(cid: int, nome: str, inicio: datetime, fim: datetime) -> dict:
    return {
        "id": cid,
        "id_dispositivo": f"RT{cid:06d}",
        "nome": nome,
        "foto_url": f"/uploads/acesso/RT{cid:06d}.jpg",
        "foto_hash": f"hash-{cid}",
        "janelas": [{"inicio": inicio.isoformat(), "fim": fim.isoformat()}],
    }


DISPOSITIVO = {
    "id": 1, "nome": "Entrada", "papel": "entrada", "modelo": "SS 3531 MF LITE",
    "host": "192.168.1.108", "porta": 80, "usuario": "admin", "senha": "x",
}


def teste_janela_controla_liberacao():
    """Só quem está dentro da janela fica habilitado no leitor."""
    ag = _agente()
    agora = datetime.now(timezone.utc)

    dentro = _credencial(1, "Joga agora", agora - timedelta(minutes=10), agora + timedelta(hours=1))
    depois = _credencial(2, "Joga amanhã", agora + timedelta(days=1), agora + timedelta(days=1, hours=1))

    resultados, erro = ag.reconciliar(DISPOSITIVO, [dentro, depois], agora)
    assert erro is None, erro
    assert all(r["ok"] for r in resultados), resultados

    leitor: DriverSimulado = ag.drivers[1]
    assert leitor.usuarios["RT000001"]["habilitado"] is True, "quem joga agora deveria estar liberado"
    assert leitor.usuarios["RT000002"]["habilitado"] is False, "jogo de amanhã não libera hoje"
    # Os dois ficam cadastrados: a foto sobe antes, o que muda é o liga/desliga.
    assert set(leitor.faces) == {"RT000001", "RT000002"}
    print("ok  janela controla a liberação")


def teste_janela_fecha_sozinha():
    """Passado o fim da janela, a pessoa é desabilitada no ciclo seguinte."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Terminou", agora - timedelta(hours=2), agora - timedelta(minutes=1))

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    assert leitor.usuarios["RT000001"]["habilitado"] is False
    print("ok  janela vencida desabilita")


def teste_foto_so_sobe_quando_muda():
    """A foto é o payload pesado: não pode ir a cada ciclo."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Alguém", agora - timedelta(minutes=5), agora + timedelta(hours=1))

    enviadas = []
    ag.baixar_foto = lambda url: (enviadas.append(url), b"foto")[1]

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert len(enviadas) == 1, f"a foto subiu {len(enviadas)}x; deveria ser 1"

    cred["foto_hash"] = "hash-novo"       # a pessoa trocou a selfie
    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert len(enviadas) == 2, "selfie trocada deveria reenviar"
    print("ok  foto só sobe quando muda")


def teste_remove_sobra_mas_poupa_cadastro_manual():
    """Limpa o que é nosso e não encosta em usuário cadastrado à mão."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Atual", agora - timedelta(minutes=5), agora + timedelta(hours=1))

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    leitor.gravar_usuario("RT000099", "Jogo antigo", True)   # sobra nossa
    leitor.gravar_usuario("ZELADOR", "Zelador", True)        # cadastro do dono

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert "RT000099" not in leitor.usuarios, "sobra do sistema deveria sair"
    assert "ZELADOR" in leitor.usuarios, "cadastro manual não pode ser apagado"
    print("ok  remove sobra e poupa cadastro manual")


def teste_leitor_fora_do_ar_nao_derruba_o_ciclo():
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Alguém", agora, agora + timedelta(hours=1))

    ag.reconciliar(DISPOSITIVO, [cred], agora)

    def explode():
        raise OSError("rede inacessível")

    ag.drivers[1].testar = explode
    resultados, erro = ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert erro is not None and "rede inacessível" in erro
    assert resultados == []
    print("ok  leitor fora do ar vira erro, não exceção")


def teste_eventos_viram_entrada_e_saida():
    """O tipo do evento sai do papel do leitor, não do equipamento."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Passante", agora - timedelta(minutes=5), agora + timedelta(hours=1))

    saida_disp = dict(DISPOSITIVO, id=2, nome="Saída", papel="saida")
    ag.reconciliar(DISPOSITIVO, [cred], agora)
    ag.reconciliar(saida_disp, [cred], agora)

    ag.drivers[1].simular_passagem("RT000001", liberado=True)
    ag.drivers[2].simular_passagem("RT000001", liberado=True)
    ag.drivers[2].simular_passagem("RT999999", liberado=False)

    eventos = ag.coletar_eventos(DISPOSITIVO) + ag.coletar_eventos(saida_disp)
    tipos = [e["tipo"] for e in eventos]
    assert tipos == ["entrada", "saida", "negado"], tipos
    # Chave única por leitor + registro: é o que impede duplicata no reenvio.
    assert len({e["chave_externa"] for e in eventos}) == 3
    print("ok  eventos viram entrada/saída/negado")


def teste_sem_janela_ninguem_entra():
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Sem jogo", agora, agora + timedelta(hours=1))
    cred["janelas"] = []

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert ag.drivers[1].usuarios["RT000001"]["habilitado"] is False
    print("ok  sem janela ninguém é liberado")


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("teste_")]
    falhas = 0
    for t in testes:
        try:
            t()
        except AssertionError as exc:
            falhas += 1
            print(f"FALHOU  {t.__name__}: {exc}")
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
