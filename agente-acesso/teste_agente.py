"""Testes do agente e dos drivers.

Rodam sem servidor e sem hardware: o servidor é um dublê e os leitores são o
`DriverSimulado`. Cobrem a parte difícil — a janela de horário, a reconciliação
e a leitura das respostas do equipamento no formato que a coleção Postman
oficial documenta.

    python teste_agente.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from agente import Agente
from driver import VALIDADE_BLOQUEADO, DriverSimulado, _ler_eventos, _ler_usuarios, formatar_data


class HttpDuble:
    """Responde no lugar do servidor. Qualquer chamada não prevista é erro."""

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


def _credencial(cid: int, nome: str, *janelas: tuple[datetime, datetime]) -> dict:
    return {
        "id": cid,
        "id_dispositivo": f"RT{cid:06d}",
        "nome": nome,
        "foto_url": f"/uploads/acesso/RT{cid:06d}.jpg",
        "foto_hash": f"hash-{cid}",
        "janelas": [{"inicio": i.isoformat(), "fim": f.isoformat()} for i, f in janelas],
    }


DISPOSITIVO = {
    "id": 1, "nome": "Entrada", "papel": "entrada", "modelo": "SS 3531 MF LITE",
    "host": "192.168.1.108", "porta": 80, "usuario": "admin", "senha": "x",
}


# ── Janela de horário ────────────────────────────────────────────────────────

def teste_validade_seleciona_a_janela_em_curso():
    """Com um jogo agora e outro amanhã, vale o de agora."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Joga agora",
                       (agora - timedelta(minutes=10), agora + timedelta(hours=1)),
                       (agora + timedelta(days=1), agora + timedelta(days=1, hours=1)))

    resultados, erro = ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert erro is None, erro
    assert all(r["ok"] for r in resultados), resultados

    leitor: DriverSimulado = ag.drivers[1]
    assert leitor.liberado_agora("RT000001"), "quem joga agora deveria passar"
    assert leitor.usuarios["RT000001"]["valido_ate"] == formatar_data(agora + timedelta(hours=1))
    print("ok  validade segue a janela em curso")


def teste_validade_aponta_para_a_proxima_quando_nao_ha_jogo_agora():
    ag = _agente()
    agora = datetime.now(timezone.utc)
    amanha = agora + timedelta(days=1)
    cred = _credencial(1, "Joga amanhã", (amanha, amanha + timedelta(hours=1)))

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    assert not leitor.liberado_agora("RT000001"), "jogo de amanhã não libera hoje"
    assert leitor.usuarios["RT000001"]["valido_de"] == formatar_data(amanha)
    print("ok  validade aponta para a próxima janela")


def teste_avanca_para_a_janela_seguinte_quando_a_atual_termina():
    """O leitor guarda um intervalo só; o agente move de um jogo para o outro."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    seguinte = (agora + timedelta(days=2), agora + timedelta(days=2, hours=1))
    cred = _credencial(1, "Dois jogos",
                       (agora - timedelta(minutes=5), agora + timedelta(hours=1)), seguinte)

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    assert leitor.usuarios["RT000001"]["valido_de"] == formatar_data(agora - timedelta(minutes=5))

    # Passa o tempo: o primeiro jogo acabou.
    depois = agora + timedelta(hours=2)
    ag.reconciliar(DISPOSITIVO, [cred], depois)
    assert leitor.usuarios["RT000001"]["valido_de"] == formatar_data(seguinte[0]), \
        "deveria ter avançado para o jogo seguinte"
    print("ok  avança da janela vencida para a seguinte")


def teste_sem_janela_fica_bloqueado_mas_cadastrado():
    """Sem jogo, a pessoa não passa — mas continua no leitor, com a foto."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Sem jogo")

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    assert not leitor.liberado_agora("RT000001")
    assert leitor.usuarios["RT000001"]["valido_de"] == VALIDADE_BLOQUEADO[0]
    # Continuar cadastrado evita reenviar a foto na próxima reserva.
    assert "RT000001" in leitor.faces
    print("ok  sem janela: bloqueado, porém cadastrado")


# ── Sincronização ────────────────────────────────────────────────────────────

def teste_foto_so_sobe_quando_muda():
    """A foto é o payload pesado: não pode ir a cada ciclo."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Alguém", (agora - timedelta(minutes=5), agora + timedelta(hours=1)))

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
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Atual", (agora - timedelta(minutes=5), agora + timedelta(hours=1)))

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    leitor: DriverSimulado = ag.drivers[1]
    leitor.gravar_usuario("RT000099", "Jogo antigo", *VALIDADE_BLOQUEADO)  # sobra nossa
    leitor.gravar_usuario("ZELADOR", "Zelador", "2020-01-01 00:00:00", "2037-01-01 00:00:00")

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert "RT000099" not in leitor.usuarios, "sobra do sistema deveria sair"
    assert "ZELADOR" in leitor.usuarios, "cadastro manual não pode ser apagado"
    print("ok  remove sobra e poupa cadastro manual")


def teste_leitor_fora_do_ar_nao_derruba_o_ciclo():
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Alguém", (agora, agora + timedelta(hours=1)))

    ag.reconciliar(DISPOSITIVO, [cred], agora)

    def explode():
        raise OSError("rede inacessível")

    ag.drivers[1].testar = explode
    resultados, erro = ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert erro is not None and "rede inacessível" in erro
    assert resultados == []
    print("ok  leitor fora do ar vira erro, não exceção")


def teste_ntp_configurado_uma_vez_por_leitor():
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Alguém", (agora, agora + timedelta(hours=1)))

    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert ag.drivers[1].ntp == "a.ntp.br"
    chamadas = []
    ag.drivers[1].configurar_ntp = lambda s: chamadas.append(s)
    ag.reconciliar(DISPOSITIVO, [cred], agora)
    assert chamadas == [], "NTP não deveria ser reconfigurado a cada ciclo"
    print("ok  NTP configurado uma vez por leitor")


def teste_eventos_viram_entrada_e_saida():
    """O tipo do evento sai do papel do leitor, não do equipamento."""
    ag = _agente()
    agora = datetime.now(timezone.utc)
    cred = _credencial(1, "Passante", (agora - timedelta(minutes=5), agora + timedelta(hours=1)))

    saida_disp = dict(DISPOSITIVO, id=2, nome="Saída", papel="saida")
    ag.reconciliar(DISPOSITIVO, [cred], agora)
    ag.reconciliar(saida_disp, [cred], agora)

    ag.drivers[1].simular_passagem("RT000001")
    ag.drivers[2].simular_passagem("RT000001")
    ag.drivers[2].simular_passagem("RT999999")   # não cadastrado: negado

    eventos = ag.coletar_eventos(DISPOSITIVO) + ag.coletar_eventos(saida_disp)
    tipos = [e["tipo"] for e in eventos]
    assert tipos == ["entrada", "saida", "negado"], tipos
    # Chave única por leitor + registro: é o que impede duplicata no reenvio.
    assert len({e["chave_externa"] for e in eventos}) == 3
    print("ok  eventos viram entrada/saída/negado")


# ── Leitura das respostas do equipamento ─────────────────────────────────────

def teste_le_usuarios_em_json():
    """Formato da V2 (AccessUser.cgi), conforme a coleção oficial."""
    texto = """{"UserList":[
      {"UserID":"RT000001","UserName":"Ana","ValidFrom":"2026-09-07 18:45:00",
       "ValidTo":"2026-09-07 20:15:00","UserStatus":0},
      {"UserID":"RT000002","UserName":"Bruno","ValidFrom":"2000-01-01 00:00:00",
       "ValidTo":"2000-01-01 00:00:01","UserStatus":0}]}"""
    u = _ler_usuarios(texto)
    assert set(u) == {"RT000001", "RT000002"}
    assert u["RT000001"]["nome"] == "Ana"
    assert u["RT000001"]["valido_ate"] == "2026-09-07 20:15:00"
    print("ok  lê usuários em JSON")


def teste_le_usuarios_em_chave_valor():
    """O portal documenta que a mesma API pode responder chave=valor."""
    texto = (
        "records[0].UserID=RT000001\r\n"
        "records[0].UserName=Ana\r\n"
        "records[0].ValidFrom=2026-09-07 18:45:00\r\n"
        "records[0].ValidTo=2026-09-07 20:15:00\r\n"
        "records[1].UserID=RT000002\r\n"
        "records[1].UserName=Bruno\r\n"
        "found=2\r\n"
    )
    u = _ler_usuarios(texto)
    assert set(u) == {"RT000001", "RT000002"}
    assert u["RT000001"]["valido_de"] == "2026-09-07 18:45:00"
    print("ok  lê usuários em chave=valor")


def teste_le_eventos_do_recordfinder():
    texto = (
        "records[0].RecNo=1201\r\n"
        "records[0].UserID=RT000001\r\n"
        "records[0].CardName=Ana\r\n"
        "records[0].CreateTime=2026-09-07 18:52:11\r\n"
        "records[0].Status=1\r\n"
        "records[1].RecNo=1202\r\n"
        "records[1].UserID=\r\n"
        "records[1].CreateTime=2026-09-07 20:03:40\r\n"
        "records[1].Status=0\r\n"
        "records[1].ErrorCode=face nao reconhecida\r\n"
    )
    ev = _ler_eventos(texto)
    assert len(ev) == 2
    assert ev[0]["liberado"] is True and ev[0]["id_registro"] == "1201"
    assert ev[1]["liberado"] is False and ev[1]["motivo"] == "face nao reconhecida"
    assert ev[1]["id_dispositivo"] is None, "campo vazio deve virar None, não string vazia"
    print("ok  lê eventos do recordFinder")


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
