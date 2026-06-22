from fastapi import APIRouter

from app.api.v1 import admin, auth, bookings, matches, players, seasons, subscriptions, webhooks

router = APIRouter()

router.include_router(auth.router)
router.include_router(players.router)
router.include_router(bookings.router)
router.include_router(matches.router)
router.include_router(subscriptions.router)
router.include_router(webhooks.router)
router.include_router(seasons.router)
router.include_router(admin.router)
