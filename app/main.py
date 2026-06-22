import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_router
from app.core.config import settings

_UPLOADS_DIR = "/app/uploads"
os.makedirs(_UPLOADS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


async def _scheduler_loop() -> None:
    """Roda a cada hora: verifica expirações e envia avisos de vencimento."""
    from app.core.database import async_session_factory
    from app.services.subscription_service import SubscriptionService

    await asyncio.sleep(60)  # aguarda o app subir completamente
    while True:
        try:
            async with async_session_factory() as db:
                svc = SubscriptionService(db)
                expiradas = await svc.verificar_expiracoes()
                avisos = await svc.enviar_avisos_vencimento()
                if expiradas or avisos:
                    logger.info("Scheduler: %d expiradas, %d avisos enviados", expiradas, avisos)
        except Exception as exc:
            logger.error("Scheduler error: %s", exc)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()


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

app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
