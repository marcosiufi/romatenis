"""Cifra simétrica para segredos guardados no banco.

Usado nas senhas dos leitores de acesso: elas precisam ficar no banco porque o
admin as cadastra pelo painel e o agente da quadra as busca depois — mas em
texto puro qualquer dump ou backup do banco entregaria o controle do portão.

A chave sai do SECRET_KEY do `.env`, então o banco sozinho não abre nada. Não é
proteção contra quem já tem o servidor inteiro: é para separar o banco do
segredo, que são as duas coisas que costumam vazar por caminhos diferentes.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIXO = "enc:v1:"


def _chave() -> bytes:
    """Deriva uma chave Fernet de 32 bytes a partir do SECRET_KEY."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def cifrar(texto: str) -> str:
    """Cifra um segredo. String vazia continua vazia — ausência não é segredo."""
    if not texto:
        return ""
    token = Fernet(_chave()).encrypt(texto.encode("utf-8")).decode("ascii")
    return _PREFIXO + token


def decifrar(valor: str) -> str:
    """Devolve o segredo em texto puro.

    Valor sem o prefixo é devolvido como está: cobre linhas gravadas antes desta
    camada existir e evita que uma migração incompleta derrube a integração.
    """
    if not valor:
        return ""
    if not valor.startswith(_PREFIXO):
        return valor
    try:
        return Fernet(_chave()).decrypt(valor[len(_PREFIXO):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        # SECRET_KEY trocado depois de gravar: o segredo é irrecuperável e o
        # admin precisa recadastrar. Devolver vazio faz o agente falhar com
        # "senha não configurada" em vez de tentar autenticar com lixo.
        return ""


def mascarar(valor: str) -> str:
    """Forma segura de mostrar no painel: só diz se existe, nunca o conteúdo."""
    return "••••••••" if valor else ""
