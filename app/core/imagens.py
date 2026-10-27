"""Fotos enviadas pelo usuário: o tipo sai dos primeiros bytes, não do nome.

O nome do arquivo é escolhido por quem envia e não prova nada; a extensão
gravada no disco vem do conteúdo. Os nomes gerados levam um sufixo aleatório:
a pasta `/uploads` é servida sem login, e `12.jpg` ou `RT000012.jpg` permitiria
enumerar o rosto de todo associado e convidado.
"""
import os
import secrets

TAMANHO_MAX_FOTO = 5 * 1024 * 1024  # 5 MB


def extensao_da_imagem(conteudo: bytes) -> str | None:
    """'.jpg', '.png' ou '.webp' conforme a assinatura do arquivo; None se não for imagem."""
    if conteudo[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if conteudo[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return ".webp"
    return None


def nome_de_foto(prefixo: str, extensao: str) -> str:
    """`prefixo-<24 hex aleatórios>.ext` — impossível de adivinhar."""
    return f"{prefixo}-{secrets.token_hex(12)}{extensao}"


def apagar_foto_antiga(url: str | None, pasta: str) -> None:
    """Remove o arquivo apontado por uma URL /uploads/..., só se estiver dentro de `pasta`.

    Sem isto cada troca de foto deixaria a anterior para trás, acessível para
    sempre por quem tivesse guardado o link.
    """
    if not url:
        return
    nome = os.path.basename(url)
    caminho = os.path.join(pasta, nome)
    if os.path.dirname(os.path.abspath(caminho)) != os.path.abspath(pasta):
        return
    try:
        os.remove(caminho)
    except OSError:
        pass
