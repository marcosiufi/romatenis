import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import router as api_router
from app.core.config import settings

# Recusa subir em produção com o segredo de desenvolvimento (Settings.conferir)
settings.conferir()

_UPLOADS_DIR = "/app/uploads"
os.makedirs(_UPLOADS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

# Chaves das travas do agendador (pg_try_advisory_xact_lock). O uvicorn sobe
# dois workers e cada um rodaria os laços abaixo: aviso de vencimento sairia
# em dobro, convocação da fila seria feita duas vezes. A trava no banco deixa
# um só executar o ciclo; o outro pula e tenta no ciclo seguinte.
_TRAVA_SCHEDULER = 7_425_001
_TRAVA_EXPIRAR = 7_425_002


async def _com_trava(chave: int, corpo) -> bool:
    """Roda `corpo()` só se conseguir a trava; devolve False se outro worker a tem.

    A trava é de transação: a conexão fica numa transação aberta enquanto o
    corpo roda (ele usa sessão própria) e a trava some sozinha no fim, mesmo
    se o corpo estourar — não há como ficar presa.
    """
    from app.core.database import engine

    async with engine.connect() as conn:
        async with conn.begin():
            obteve = await conn.scalar(
                text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": chave}
            )
            if not obteve:
                return False
            await corpo()
    return True


async def _ciclo_scheduler() -> None:
    from app.core.database import async_session_factory
    from app.services.match_service import MatchService
    from app.services.subscription_service import SubscriptionService

    async with async_session_factory() as db:
        svc = SubscriptionService(db)
        expiradas = await svc.verificar_expiracoes()
        # Quem venceu há mais de 7 dias sem renovar sai de "renovação" e vira
        # inativo — sem isto ficava em renovação para sempre, visível no ranking.
        renovacoes = await svc.expirar_renovacao()
        avisos = await svc.enviar_avisos_vencimento()
        resetados = await svc.resetar_nivel_inativos()
        # Sem isto a fila trava: uma convocação não atendida segura a
        # vaga para sempre e ninguém mais é chamado.
        convocacoes = await svc.verificar_convocacoes_expiradas()
        lembretes = await svc.enviar_lembretes_contrato()
        partidas = await MatchService(db).enviar_lembretes_partida()
        if any((expiradas, renovacoes, avisos, resetados, convocacoes, lembretes, partidas)):
            logger.info(
                "Scheduler: %d expiradas, %d renovacoes vencidas, %d avisos, "
                "%d niveis zerados, %d convocacoes expiradas, %d lembretes de "
                "contrato, %d lembretes de partida",
                expiradas, renovacoes, avisos, resetados, convocacoes, lembretes, partidas,
            )


async def _scheduler_loop() -> None:
    """Roda a cada hora: expirações, avisos de vencimento, fila e contratos."""
    await asyncio.sleep(60)  # aguarda o app subir completamente
    while True:
        try:
            await _com_trava(_TRAVA_SCHEDULER, _ciclo_scheduler)
        except Exception as exc:
            logger.error("Scheduler error: %s", exc)
        await asyncio.sleep(3600)


async def _ciclo_expirar_reservas() -> None:
    from sqlalchemy import and_, select

    from app.core.database import async_session_factory
    from app.models.booking import Booking, StatusReserva, TipoReserva
    from app.models.match import Match, StatusPartida
    from app.models.payment import Payment, StatusPagamento
    from app.services import cupom_service
    from app.services.acesso_service import AcessoService
    from app.services.asaas_client import AsaasClient

    # Ambos geram cobrança antes de confirmar o horário
    TIPOS_COM_PAGAMENTO = (TipoReserva.LOCACAO_AVULSA, TipoReserva.JOGO_AVULSO)

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with async_session_factory() as db:
        expiradas = (await db.execute(
            select(Booking).where(
                and_(
                    Booking.status == StatusReserva.AGUARDANDO_PAGAMENTO,
                    Booking.tipo.in_(TIPOS_COM_PAGAMENTO),
                    Booking.criado_em <= cutoff,
                )
            )
        )).scalars().all()

        for booking in expiradas:
            booking.status = StatusReserva.CANCELADA
            # Jogo avulso cria uma partida junto: cancela também, senão
            # ela segue "agendada" e consome a cota semanal do jogador.
            if booking.match_id:
                match = await db.get(Match, booking.match_id)
                if match and match.status == StatusPartida.AGENDADO:
                    match.status = StatusPartida.CANCELADO_SEM_PLACAR
            payment = await db.scalar(
                select(Payment).where(Payment.booking_id == booking.id)
            )
            if payment and payment.gateway_id and payment.status == StatusPagamento.PENDENTE:
                try:
                    await AsaasClient().cancelar_cobranca(payment.gateway_id)
                except Exception:
                    pass
                payment.status = StatusPagamento.FALHOU
                # Cupom foi contado na criação; a pré-reserva expirou sem
                # pagar, então devolve a vaga do cupom.
                if payment.cupom_codigo:
                    await cupom_service.devolver_uso(db, payment.cupom_codigo)

        if expiradas:
            await db.commit()
            # A pré-reserva já tinha janela no portão; cancelada, perde o acesso.
            for booking in expiradas:
                await AcessoService(db).revogar_booking(booking.id)
            logger.info("Reservas expiradas canceladas: %d", len(expiradas))


async def _expirar_reservas_loop() -> None:
    """A cada 2 min: cancela pré-reservas não pagas há mais de 10 min."""
    await asyncio.sleep(30)
    while True:
        try:
            await _com_trava(_TRAVA_EXPIRAR, _ciclo_expirar_reservas)
        except Exception as exc:
            logger.error("Expirar reservas error: %s", exc)
        await asyncio.sleep(120)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.access(_UPLOADS_DIR, os.W_OK):
        # O container roda sem root (uid 10001); a pasta montada do host
        # precisa pertencer a ele, senão nenhuma foto é gravada.
        logger.error(
            "A pasta de uploads %s não é gravável pelo usuário do container. "
            "No servidor: chown -R 10001:10001 /opt/romatenis/uploads",
            _UPLOADS_DIR,
        )
    task1 = asyncio.create_task(_scheduler_loop())
    task2 = asyncio.create_task(_expirar_reservas_loop())
    yield
    task1.cancel()
    task2.cancel()


app = FastAPI(
    title="Roma Tênis",
    version="0.1.0",
    docs_url="/api/docs" if not settings.producao else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.producao else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Política de conteúdo: só o próprio domínio carrega script, e nada daqui pode
# ser embutido em iframe de outro site. 'unsafe-inline' em script é exigido
# pelos handlers onclick e pelo módulo de tema no <head>; mesmo assim a regra
# impede o carregamento de script de qualquer outro domínio. Fontes: Google
# (Cinzel do logotipo) e /fonts. Imagens: data: (QR do PIX) e blob: (prévia
# da selfie). viacep: busca de CEP no site.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self' https://viacep.com.br",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    cab = resposta.headers
    cab.setdefault("Content-Security-Policy", _CSP)
    cab.setdefault("X-Content-Type-Options", "nosniff")
    cab.setdefault("X-Frame-Options", "DENY")
    cab.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    cab.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=()")
    if request.url.path.startswith("/uploads/"):
        # Fotos de pessoas: o navegador guarda só para o próprio usuário, e
        # proxies no caminho não.
        cab["Cache-Control"] = "private, max-age=3600"
    return resposta


app.include_router(api_router, prefix="/api/v1")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/redefinir-senha", include_in_schema=False)
async def redefinir_senha_page():
    return FileResponse("frontend/redefinir-senha.html")


@app.get("/selfie/{token}", include_in_schema=False)
async def selfie_page(token: str):
    """Página onde quem não tem login envia a foto do rosto.

    O token não é validado aqui: a página o valida por API antes de mostrar a
    câmera. Servir o HTML para qualquer token evita distinguir link inválido de
    link válido pelo código HTTP.
    """
    return FileResponse("frontend/selfie.html")


app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
