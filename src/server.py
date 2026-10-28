"""ASGI entrypoint that runs the bot behind FastAPI.

With a public URL (WEBHOOK_URL, or RENDER_EXTERNAL_URL on Render), Telegram
delivers updates to POST /telegram. Without one, the dev bot polls instead.
"""

import hashlib
import hmac
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from utils.constants import Environment

WEBHOOK_PATH = "/telegram"

logger = logging.getLogger(__name__)


def webhook_secret(token: str) -> str:
    """Derive the webhook secret from the bot token, so no extra config is needed."""
    return hashlib.sha256(f"webhook:{token}".encode()).hexdigest()


def create_app(
    build_application: Callable[[Environment], Application],
    env: Environment,
    base_url: str | None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if env == Environment.PROD and not base_url:
            # Polling would delete the prod webhook and steal its updates
            raise RuntimeError("Set WEBHOOK_URL or RENDER_EXTERNAL_URL in prod")

        application = build_application(env)
        app.state.application = application
        app.state.secret = webhook_secret(application.bot.token)

        await application.initialize()
        if base_url:
            url = base_url.rstrip("/") + WEBHOOK_PATH
            await application.bot.set_webhook(
                url=url,
                secret_token=app.state.secret,
                allowed_updates=Update.ALL_TYPES,
            )
            logger.info("Receiving updates by webhook at %s", url)
        else:
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("Receiving updates by polling")
        await application.start()
        try:
            yield
        finally:
            # Leave the webhook registered: during a deploy the new instance
            # has already set it, and deleting it here would cut that one off.
            if application.updater and application.updater.running:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    def health():
        return {"status": "ok"}

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: Annotated[str, Header()] = "",
    ):
        # Compare bytes: compare_digest rejects non-ASCII str with TypeError
        if not hmac.compare_digest(
            x_telegram_bot_api_secret_token.encode(), request.app.state.secret.encode()
        ):
            raise HTTPException(status_code=403)
        application: Application = request.app.state.application
        update = Update.de_json(await request.json(), application.bot)
        await application.update_queue.put(update)
        return Response(status_code=200)

    return app


def main() -> FastAPI:
    from src.bot import build_application

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    env = Environment(os.getenv("BOT_ENV", Environment.PROD))
    base_url = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL")
    logger.info("Starting bot (%s)...", env)
    return create_app(build_application, env, base_url)
