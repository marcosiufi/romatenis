"""Renomeia as fotos já gravadas para nomes impossíveis de adivinhar.

Antes da auditoria de 27/10/2026, /uploads/avatars/12.jpg e
/uploads/acesso/RT000012.jpg eram públicos e enumeráveis: qualquer pessoa na
internet baixava o rosto de todo associado e convidado. As fotos novas já saem
com sufixo aleatório (app/core/imagens.py); este script trata as antigas.

Idempotente: pula o que já tem sufixo. Rode uma vez depois do deploy:

    docker compose exec -T api python scripts/proteger_fotos.py
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.imagens import nome_de_foto
from app.models.acesso import CredencialAcesso
from app.models.convidado import Convidado
from app.models.player import Player

RAIZ = "/app/uploads"
# Nome antigo: prefixo sem hífen + extensão. Os novos têm "-<24 hex>".
_ANTIGO = re.compile(r"^(?P<prefixo>[A-Za-z0-9]+)(?P<ext>\.(?:jpg|jpeg|png|webp))$", re.I)
_URL = re.compile(r"^/uploads/(?P<pasta>avatars|acesso)/(?P<nome>[^/]+)$")


def _destino(url: str) -> tuple[str, str, str] | None:
    m = _URL.match(url or "")
    if not m:
        return None
    pasta, nome = m.group("pasta"), m.group("nome")
    mo = _ANTIGO.match(nome)
    if not mo:
        return None  # já protegida, ou formato que não conhecemos
    return pasta, nome, nome_de_foto(mo.group("prefixo"), mo.group("ext").lower())


async def main() -> None:
    renomeadas: dict[str, str] = {}  # url antiga → nova (player e credencial apontam para a mesma foto)

    async with AsyncSessionLocal() as db:
        for modelo in (Player, Convidado, CredencialAcesso):
            linhas = (await db.execute(select(modelo).where(modelo.foto_url.is_not(None)))).scalars().all()
            for obj in linhas:
                url = obj.foto_url
                if url in renomeadas:
                    obj.foto_url = renomeadas[url]
                    continue
                alvo = _destino(url)
                if alvo is None:
                    continue
                pasta, nome, novo = alvo
                origem = os.path.join(RAIZ, pasta, nome)
                if not os.path.exists(origem):
                    print(f"aviso: {url} não existe no disco; registro mantido")
                    continue
                os.rename(origem, os.path.join(RAIZ, pasta, novo))
                obj.foto_url = renomeadas[url] = f"/uploads/{pasta}/{novo}"
        await db.commit()

    print(f"{len(renomeadas)} foto(s) renomeada(s).")


if __name__ == "__main__":
    asyncio.run(main())
