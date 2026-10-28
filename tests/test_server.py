from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.server import WEBHOOK_PATH, create_app, webhook_secret
from utils.constants import Environment

TOKEN = "123:abc"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def fake_application():
    application = MagicMock()
    application.bot.token = TOKEN
    application.bot.set_webhook = AsyncMock()
    application.updater.start_polling = AsyncMock()
    application.updater.stop = AsyncMock()
    application.updater.running = False
    for name in ("initialize", "start", "stop", "shutdown"):
        setattr(application, name, AsyncMock())
    application.update_queue.put = AsyncMock()
    return application


def client_for(env, base_url, application):
    return TestClient(create_app(lambda _env: application, env, base_url))


def test_webhook_mode_registers_webhook_and_keeps_it_on_shutdown():
    application = fake_application()
    with client_for(Environment.PROD, "https://bot.example.com/", application) as c:
        assert c.get("/").json() == {"status": "ok"}

    application.bot.set_webhook.assert_awaited_once()
    kwargs = application.bot.set_webhook.call_args.kwargs
    assert kwargs["url"] == "https://bot.example.com/telegram"
    assert kwargs["secret_token"] == webhook_secret(TOKEN)
    application.updater.start_polling.assert_not_awaited()
    application.bot.delete_webhook.assert_not_called()
    application.stop.assert_awaited_once()
    application.shutdown.assert_awaited_once()


def test_webhook_queues_update_with_valid_secret():
    application = fake_application()
    with client_for(Environment.PROD, "https://bot.example.com", application) as c:
        response = c.post(
            WEBHOOK_PATH,
            json={"update_id": 1},
            headers={SECRET_HEADER: webhook_secret(TOKEN)},
        )

    assert response.status_code == 200
    update = application.update_queue.put.call_args.args[0]
    assert update.update_id == 1


@pytest.mark.parametrize(
    "headers",
    [{}, {SECRET_HEADER: "wrong"}, {SECRET_HEADER: "caf\u00e9".encode("latin-1")}],
)
def test_webhook_rejects_bad_secret(headers):
    application = fake_application()
    with client_for(Environment.PROD, "https://bot.example.com", application) as c:
        response = c.post(WEBHOOK_PATH, json={"update_id": 1}, headers=headers)

    assert response.status_code == 403
    application.update_queue.put.assert_not_awaited()


def test_dev_without_url_polls():
    application = fake_application()
    with client_for(Environment.DEV, None, application):
        application.updater.running = True

    application.updater.start_polling.assert_awaited_once()
    application.bot.set_webhook.assert_not_awaited()
    application.updater.stop.assert_awaited_once()


def test_prod_without_url_refuses_to_start():
    application = fake_application()
    with (
        pytest.raises(RuntimeError, match="WEBHOOK_URL"),
        client_for(Environment.PROD, None, application),
    ):
        pass

    application.initialize.assert_not_awaited()
