"""Endpoints do controle de acesso.

Dois públicos, nenhum deles é o app do associado:

- **o agente da quadra**, que autentica por um token único e busca o estado
  desejado, devolve eventos e reporta o que sincronizou;
- **quem não tem login** (convidado de jogo avulso, cliente de locação) e
  precisa enviar a selfie por um link com token.

O servidor nunca inicia conexão — é sempre o agente que busca. Ver o docstring
de `app.models.acesso` para o porquê.
"""
import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cripto import decifrar
from app.core.database import get_db
from app.core.imagens import TAMANHO_MAX_FOTO, extensao_da_imagem
from app.core.limite import por_ip
from app.models.acesso import TipoEventoAcesso
from app.models.configuracao import Configuracao
from app.services.acesso_service import AcessoError, AcessoService

router = APIRouter(prefix="/acesso", tags=["acesso"])


# ── Autenticação do agente ───────────────────────────────────────────────────

async def agente_autenticado(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Valida o token do agente da quadra.

    Comparação em tempo constante: o token dá controle sobre o portão, e a
    diferença de tempo de um `==` comum vaza o prefixo correto byte a byte.
    """
    cfg = await Configuracao.get(db)
    esperado = decifrar(cfg.acesso_agente_token)
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token do agente não configurado no painel.",
        )
    recebido = (authorization or "").removeprefix("Bearer ").strip()
    if not recebido or not secrets.compare_digest(recebido, esperado):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token do agente inválido.",
        )


# ── Contratos com o agente ───────────────────────────────────────────────────

class EventoIn(BaseModel):
    chave_externa: str = Field(min_length=1, max_length=120)
    tipo: TipoEventoAcesso          # entrada | saida | negado | abertura_remota
    momento: datetime               # ISO 8601 com fuso
    id_dispositivo: str | None = Field(default=None, max_length=20)   # o "RT000123" lido pelo leitor
    dispositivo_id: int | None = None
    nome_lido: str | None = Field(default=None, max_length=150)
    motivo: str | None = Field(default=None, max_length=200)


class ResultadoSincronizacao(BaseModel):
    credencial_id: int
    ok: bool
    erro: str | None = None


class SaudeDispositivo(BaseModel):
    id: int
    ok: bool
    erro: str | None = None


class RelatorioIn(BaseModel):
    dispositivos: list[SaudeDispositivo] = []
    credenciais: list[ResultadoSincronizacao] = []
    eventos: list[EventoIn] = []


class ResultadoComando(BaseModel):
    comando_id: int
    ok: bool
    erro: str | None = None


# ── Rotas do agente ──────────────────────────────────────────────────────────

@router.get("/agente/estado", dependencies=[Depends(agente_autenticado)])
async def estado_do_agente(db: Annotated[AsyncSession, Depends(get_db)]):
    """Estado desejado completo: leitores, pessoas e janelas.

    Devolve tudo, não um diff — é o que permite o agente se recuperar sozinho de
    qualquer dessincronia, inclusive de alguém ter mexido na tela do leitor.
    """
    servico = AcessoService(db)
    estado = await servico.estado_para_agente()
    estado["comandos"] = [
        {"id": c.id, "tipo": c.tipo, "payload": c.payload}
        for c in await servico.comandos_pendentes()
    ]
    return estado


@router.post("/agente/relatorio", dependencies=[Depends(agente_autenticado)])
async def relatorio_do_agente(
    body: RelatorioIn,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Batimento do agente: saúde dos leitores, sincronizações e eventos.

    Uma chamada só, porque o agente roda num ciclo e cada ida à internet é uma
    chance de falhar. Eventos repetidos são descartados pela chave externa.
    """
    servico = AcessoService(db)
    await servico.marcar_agente_visto([d.model_dump() for d in body.dispositivos])
    if body.credenciais:
        await servico.confirmar_sincronizacao([c.model_dump() for c in body.credenciais])
    gravados = await servico.registrar_eventos([e.model_dump() for e in body.eventos])
    return {"ok": True, "eventos_gravados": gravados}


@router.post("/agente/comandos/{comando_id}", dependencies=[Depends(agente_autenticado)])
async def concluir_comando(
    comando_id: int,
    body: ResultadoComando,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await AcessoService(db).concluir_comando(comando_id, body.ok, body.erro)
    return {"ok": True}


# ── Selfie de quem não tem login ─────────────────────────────────────────────

@router.get("/selfie/{token}", dependencies=[Depends(por_ip("selfie", 30, 60))])
async def dados_do_link_de_selfie(token: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Confere o link antes de mostrar a câmera, para não pedir foto à toa.

    O link só vale enquanto a pessoa tem jogo marcado: depois, trocar a foto
    não liberaria nada hoje, mas liberaria outro rosto no próximo jogo dela.
    """
    try:
        cred = await AcessoService(db).dados_do_link(token)
    except AcessoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"nome": cred.nome, "ja_enviou": bool(cred.foto_hash)}


@router.post("/selfie/{token}", dependencies=[Depends(por_ip("selfie", 30, 60))])
async def enviar_selfie(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    foto: Annotated[UploadFile, File(...)],
):
    conteudo = await foto.read()
    if len(conteudo) > TAMANHO_MAX_FOTO:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Arquivo muito grande. Máximo 5 MB.",
        )
    # O tipo vem do conteúdo, não do nome do arquivo
    ext = extensao_da_imagem(conteudo)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato inválido. Use JPG, PNG ou WebP.",
        )
    try:
        cred = await AcessoService(db).registrar_selfie(token, conteudo, ext)
    except AcessoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "nome": cred.nome}
