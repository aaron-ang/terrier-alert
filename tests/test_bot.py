import os
import sys

import pendulum
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User, ForceReply, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.bot import (
    start,
    help,
    about,
    subscribe,
    unsubscribe_dialog,
    cancel,
    await_feedback,
    save_feedback,
    error_handler,
)
from src.db import Database
from utils import conv
from utils.constants import *


@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.chat = MagicMock(spec=Chat)
    update.message.from_user = MagicMock(spec=User)
    update.message.reply_text = AsyncMock()
    update.message.reply_markdown_v2 = AsyncMock()
    update.message.delete = AsyncMock()
    update.callback_query = None
    update._effective_message = update.message
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context._user_id = "123456789"
    context._chat_id = "123456789"
    context.user_data = {}
    return context


@pytest.fixture(autouse=True)
def mock_db():
    with patch("src.bot.DB") as mock:
        db = MagicMock(spec=Database)
        db.env = Environment.DEV
        db.get_user.return_value = None
        db.get_user_course.return_value = None

        mock.env = Environment.DEV
        mock.get_user = db.get_user
        mock.get_user_course = db.get_user_course
        yield mock


@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    await start(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with(
        conv.WELCOME_TEXT, quote=True
    )


@pytest.mark.asyncio
async def test_help_command(mock_update, mock_context):
    await help(mock_update, mock_context)
    mock_update.message.reply_markdown_v2.assert_called_once_with(
        conv.HELP_MD, quote=True
    )


@pytest.mark.asyncio
async def test_about_command(mock_update, mock_context):
    await about(mock_update, mock_context)
    mock_update.message.reply_markdown_v2.assert_called_once_with(
        conv.ABOUT_MD, quote=True
    )


@pytest.mark.asyncio
async def test_error_handler(mock_update, mock_context):
    mock_context.error = Exception("Test error")
    await error_handler(mock_update, mock_context)
    mock_context.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_new_user(mock_update, mock_context):
    result = await subscribe(mock_update, mock_context)
    assert result == InputStates.AWAIT_SELECTION
    assert isinstance(
        mock_update.message.reply_markdown_v2.call_args[1]["reply_markup"],
        InlineKeyboardMarkup,
    )


@pytest.mark.asyncio
async def test_subscribe_already_subscribed(mock_update, mock_context, mock_db):
    mock_context.user_data = {
        Message.IS_SUBSCRIBED: True,
        Message.COLLEGE: "CAS",
        Message.DEPARTMENT: "CS",
        Message.COURSE_NUM: "111",
        Message.SECTION: "A1",
    }
    mock_db.get_user.return_value = {
        IS_SUBSCRIBED: True,
        LAST_SUBSCRIBED: pendulum.now(),
        LAST_SUBSCRIPTION: "CAS CS111 A1",
    }

    result = await subscribe(mock_update, mock_context)
    assert result == ConversationHandler.END
    assert (
        "already subscribed"
        in mock_update.message.reply_markdown_v2.call_args[0][0].lower()
    )


@pytest.mark.asyncio
async def test_subscribe_recently_subscribed(mock_update, mock_context, mock_db):
    recent_time = pendulum.now().subtract(hours=1)
    mock_db.env = Environment.PROD
    mock_db.get_user.return_value = {
        IS_SUBSCRIBED: False,
        LAST_SUBSCRIBED: recent_time,
        LAST_SUBSCRIPTION: "CAS CS111 A1",
    }

    result = await subscribe(mock_update, mock_context)
    assert result == ConversationHandler.END
    assert (
        "recently subscribed"
        in mock_update.message.reply_markdown_v2.call_args[0][0].lower()
    )


@pytest.mark.asyncio
async def test_cancel_command(mock_update, mock_context):
    # Setup some user data to be cleared
    mock_context.user_data = {
        Message.USERNAME: "test",
        Message.PASSWORD: "secret",
        Message.INVALID_MSG_ID: 123,
    }

    # Since we're not using callback_query, bot.send_message should be called
    mock_context.bot.send_message.return_value = "Aborted."

    result = await cancel(mock_update, mock_context)

    # Verify results
    assert result == ConversationHandler.END
    assert Message.USERNAME not in mock_context.user_data
    assert Message.PASSWORD not in mock_context.user_data
    mock_context.bot.send_message.assert_called_once_with(
        mock_context._chat_id, "Aborted."
    )


@pytest.mark.asyncio
async def test_unsubscribe_dialog_not_subscribed(mock_update, mock_context, mock_db):
    mock_user = {
        IS_SUBSCRIBED: False,
        LAST_SUBSCRIBED: pendulum.now() - pendulum.duration(hours=1),
        LAST_SUBSCRIPTION: "CAS CS111 A1",
    }
    mock_db.get_user.return_value = mock_user
    mock_db.get_user_course.return_value = None

    result = await unsubscribe_dialog(mock_update, mock_context)
    assert result == ConversationHandler.END
    assert "not subscribed" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_unsubscribe_dialog_subscribed(mock_update, mock_context, mock_db):
    mock_user = {
        IS_SUBSCRIBED: True,
        LAST_SUBSCRIBED: pendulum.now(),
        LAST_SUBSCRIPTION: "CAS CS111 A1",
    }
    mock_db.get_user.return_value = mock_user
    mock_db.get_user_course.return_value = {
        COURSE_NAME: "CAS CS111 A1",
        USER_LIST: ["123456789"],
    }

    result = await unsubscribe_dialog(mock_update, mock_context)
    assert result == InputStates.AWAIT_SELECTION
    assert isinstance(
        mock_update.message.reply_text.call_args[1]["reply_markup"],
        InlineKeyboardMarkup,
    )


@pytest.mark.asyncio
async def test_unknown_command(mock_update, mock_context):
    from src.bot import unknown

    await unknown(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with(
        conv.UNKNOWN_CMD_TEXT, quote=True
    )


@pytest.mark.asyncio
async def test_feedback_flow(mock_update, mock_context):
    # Test feedback initiation
    result = await await_feedback(mock_update, mock_context)
    assert result == InputStates.AWAIT_FEEDBACK
    mock_update.message.reply_text.assert_called_once_with(
        conv.FEEDBACK_TEXT, quote=True, reply_markup=ForceReply()
    )

    mock_update.message.reply_text.reset_mock()

    # Test feedback submission
    mock_update.message.text = "Test feedback"
    mock_context.bot.send_message.return_value = AsyncMock()
    result = await save_feedback(mock_update, mock_context)

    assert result == ConversationHandler.END
    mock_context.bot.send_message.assert_called_once()
    mock_update.message.reply_text.assert_called_once_with(conv.FEEDBACK_SUCCESS_TEXT)
