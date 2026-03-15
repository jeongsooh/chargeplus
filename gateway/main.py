import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.websocket import router as websocket_router
from broker.redis_client import init_redis, close_redis
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    # Startup
    logger.info("ChargePlus Gateway starting up...")
    await init_redis(settings.REDIS_URL)
    logger.info(f"Gateway ready. Host={settings.GATEWAY_HOST} Port={settings.GATEWAY_PORT}")
    logger.info(f"OCPP Security Profile: {settings.OCPP_SECURITY_PROFILE}")

    yield

    # Shutdown
    logger.info("ChargePlus Gateway shutting down...")
    await close_redis()
    logger.info("Gateway shutdown complete.")


app = FastAPI(
    title="ChargePlus OCPP Gateway",
    description="FastAPI WebSocket Gateway for OCPP 1.6 Charging Station Management",
    version="1.0.0",
    lifespan=lifespan,
)

# Include WebSocket router
app.include_router(websocket_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "chargeplus-gateway"}


@app.get("/")
async def root():
    return {"message": "ChargePlus OCPP 1.6 Gateway", "version": "1.0.0"}
