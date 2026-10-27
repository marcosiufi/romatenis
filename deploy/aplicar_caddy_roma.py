#!/usr/bin/env python3
"""Aplica os cabeçalhos de segurança ao bloco do Roma no Caddyfile do servidor.

O Caddy deste servidor é compartilhado com os sites da SIUFI: o Caddyfile em
/opt/romatenis é mantido à mão e NÃO é o do repositório (seção 11 do
docs/SISTEMA.md). Este script só mexe dentro do bloco `romatenis.com.br { }`:

- `request_body { max_size 12MB }` — a maior entrada legítima é uma foto de 5 MB;
- `header { Strict-Transport-Security …; -Server }` — HTTPS obrigatório por um
  ano e sem anunciar o servidor. Os demais cabeçalhos (CSP, nosniff) saem da API.

É idempotente, guarda um .bak, desfaz se o Caddy não validar e recarrega sem
derrubar os outros sites (`caddy reload`, não `restart`).

    python3 /opt/romatenis/deploy/aplicar_caddy_roma.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ARQ = Path("/opt/romatenis/Caddyfile")
PROJETO = "/opt/romatenis"

REQUEST_BODY = """    # Maior envio legítimo é uma foto de 5 MB; o resto é JSON pequeno.
    request_body {
        max_size 12MB
    }
"""
HEADER = """    header {
        # Navegador só fala HTTPS com o domínio por um ano
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        # Não anuncia o servidor. CSP, nosniff e afins saem da própria API.
        -Server
    }
"""

# Só o bloco cujo nome começa a linha: `www.romatenis.com.br { }` não casa.
# O fecho é a chave em coluna zero; as chaves internas ficam indentadas.
BLOCO = re.compile(r"^romatenis\.com\.br[ \t]*\{[ \t]*\n(?P<corpo>.*?)^\}", re.S | re.M)


def aplicar(texto: str) -> str | None:
    """Devolve o Caddyfile com o bloco do Roma endurecido; None se já estava."""
    bloco = BLOCO.search(texto)
    if not bloco:
        raise ValueError("bloco `romatenis.com.br { }` não encontrado")
    corpo = bloco.group("corpo")
    acrescimos = ""
    if "request_body" not in corpo:
        acrescimos += REQUEST_BODY
    if "Strict-Transport-Security" not in corpo:
        acrescimos += HEADER
    if not acrescimos:
        return None
    return texto[: bloco.start("corpo")] + acrescimos + corpo + texto[bloco.end("corpo"):]


def caddy(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "caddy", "caddy", *args,
         "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        cwd=PROJETO, capture_output=True, text=True,
    )


def main() -> None:
    texto = ARQ.read_text(encoding="utf-8")
    try:
        novo = aplicar(texto)
    except ValueError as erro:
        sys.exit(f"{erro} em {ARQ}")
    if novo is None:
        print("já aplicado; nada a fazer")
        return

    bak = ARQ.with_name(f"Caddyfile.bak-auditoria-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(ARQ, bak)
    # Grava no mesmo inode: o container monta este arquivo, e um arquivo novo
    # no lugar (como `sed -i` faz) ficaria invisível para o Caddy até reiniciar
    ARQ.write_text(novo, encoding="utf-8")

    v = caddy("validate")
    if v.returncode != 0:
        ARQ.write_text(texto, encoding="utf-8")
        sys.exit("O Caddy não validou; Caddyfile restaurado como estava. Erro:\n"
                 + (v.stderr or v.stdout)[-1200:])

    r = caddy("reload")
    if r.returncode != 0:
        sys.exit("Validou, mas o reload falhou (o arquivo ficou atualizado). Erro:\n"
                 + (r.stderr or r.stdout)[-1200:]
                 + "\nSe for o caso, aplique com: docker compose restart caddy")

    print(f"ok: bloco do Roma atualizado (backup em {bak.name}); "
          "Caddy recarregado sem derrubar os outros sites")
    print("confira: curl -sI https://romatenis.com.br/api/health | grep -i strict-transport")


if __name__ == "__main__":
    main()
