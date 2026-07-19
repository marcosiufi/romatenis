import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_router
from app.core.config import settings

_UPLOADS_DIR = "/app/uploads"
os.makedirs(_UPLOADS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


async def _scheduler_loop() -> None:
    """Roda a cada hora: expirações, avisos de vencimento, fila e contratos."""
    from app.core.database import async_session_factory
    from app.services.subscription_service import SubscriptionService

    await asyncio.sleep(60)  # aguarda o app subir completamente
    while True:
        try:
            async with async_session_factory() as db:
                svc = SubscriptionService(db)
                expiradas = await svc.verificar_expiracoes()
                avisos = await svc.enviar_avisos_vencimento()
                resetados = await svc.resetar_nivel_inativos()
                # Sem isto a fila trava: uma convocação não atendida segura a
                # vaga para sempre e ninguém mais é chamado.
                convocacoes = await svc.verificar_convocacoes_expiradas()
                lembretes = await svc.enviar_lembretes_contrato()
                if expiradas or avisos or resetados or convocacoes or lembretes:
                    logger.info(
                        "Scheduler: %d expiradas, %d avisos, %d niveis zerados, "
                        "%d convocacoes expiradas, %d lembretes de contrato",
                        expiradas, avisos, resetados, convocacoes, lembretes,
                    )
        except Exception as exc:
            logger.error("Scheduler error: %s", exc)
        await asyncio.sleep(3600)


async def _expirar_reservas_loop() -> None:
    """A cada 2 min: cancela pré-reservas não pagas há mais de 10 min."""
    from sqlalchemy import and_, select
    from app.core.database import async_session_factory
    from app.models.booking import Booking, StatusReserva, TipoReserva
    from app.models.match import Match, StatusPartida
    from app.models.payment import Payment, StatusPagamento
    from app.services.asaas_client import AsaasClient

    # Ambos geram cobrança antes de confirmar o horário
    TIPOS_COM_PAGAMENTO = (TipoReserva.LOCACAO_AVULSA, TipoReserva.JOGO_AVULSO)

    await asyncio.sleep(30)
    while True:
        try:
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

                if expiradas:
                    await db.commit()
                    logger.info("Reservas expiradas canceladas: %d", len(expiradas))
        except Exception as exc:
            logger.error("Expirar reservas error: %s", exc)
        await asyncio.sleep(120)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task1 = asyncio.create_task(_scheduler_loop())
    task2 = asyncio.create_task(_expirar_reservas_loop())
    yield
    task1.cancel()
    task2.cancel()


app = FastAPI(
    title="Roma Tênis",
    version="0.1.0",
    docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/redefinir-senha", include_in_schema=False)
async def redefinir_senha_page():
    return FileResponse("frontend/redefinir-senha.html")


app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
