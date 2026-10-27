"""Limite de tentativas por IP e por conta.

Fecha a porta à força bruta no login, ao disparo em massa de e-mails de
redefinição e à criação de contas em série. Fica em memória, por processo:
com dois workers o limite efetivo dobra, o que ainda é ordens de grandeza
abaixo do que um ataque precisa. Não vale a pena uma tabela no banco por isso.

O IP vem de `request.client`, que o uvicorn preenche a partir do
X-Forwarded-For enviado pelo Caddy (`--proxy-headers` no Dockerfile).
"""
import time
from collections import deque

from fastapi import HTTPException, Request, status


class _Janelas:
    """Janela deslizante por chave: guarda os instantes das últimas tentativas."""

    def __init__(self) -> None:
        self._eventos: dict[str, deque[float]] = {}

    def tentar(self, chave: str, maximo: int, janela: float) -> float:
        """Registra uma tentativa. Devolve 0 se permitida, senão os segundos até liberar."""
        agora = time.monotonic()
        fila = self._eventos.get(chave)
        if fila is None:
            if len(self._eventos) > 20_000:
                self._podar(agora, janela)
            fila = self._eventos[chave] = deque()
        limite = agora - janela
        while fila and fila[0] <= limite:
            fila.popleft()
        if len(fila) >= maximo:
            return fila[0] + janela - agora
        fila.append(agora)
        return 0.0

    def _podar(self, agora: float, janela: float) -> None:
        """Esquece chaves sem tentativa recente, para a memória não crescer sem fim."""
        for chave in [c for c, f in self._eventos.items() if not f or f[-1] <= agora - max(janela, 3600)]:
            del self._eventos[chave]

    def limpar(self) -> None:
        self._eventos.clear()


_janelas = _Janelas()


def ip_do_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def exigir(chave: str, maximo: int, janela_s: int) -> None:
    """Conta uma tentativa na chave; estoura 429 quando passa do máximo na janela."""
    espera = _janelas.tentar(chave, maximo, janela_s)
    if espera > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde um pouco e tente de novo.",
            headers={"Retry-After": str(int(espera) + 1)},
        )


def por_ip(nome: str, maximo: int, janela_s: int):
    """Dependência de rota: no máximo `maximo` chamadas por IP a cada `janela_s` segundos."""

    async def _dependencia(request: Request) -> None:
        exigir(f"{nome}:ip:{ip_do_cliente(request)}", maximo, janela_s)

    return _dependencia
