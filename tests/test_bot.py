from unittest.mock import AsyncMock, MagicMock, patch

import pendulum
import pytest
from telegram import Chat, ForceReply, InlineKeyboardMarkup, Message, Update, User
from telegram.error import Conflict
from telegram.ext import ContextTypes, ConversationHandler

from src.bot import (
    about,
    await_feedback,
    cancel,
    error_handler,
    help_command,
    save_custom_input,
    save_feedback,
    start,
    subscribe,
    unsubscribe_dialog,
)
from src.db import Database
from utils.constants import (
    COURSE_NAME,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED,
    LAST_SUBSCRIPTION,
    USER_LIST,
    Environment,
    InputStates,
)
from utils.constants import (
    Message as MsgEnum,
)
from utils.conv import (
    ABOUT_MD,
    FEEDBACK_SUCCESS_TEXT,
    FEEDBACK_TEXT,
    HELP_MD,
    UNKNOWN_CMD_TEXT,
    welcome_text,
)


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
    update.effective_message = update.message
    update.effective_user = MagicMock(spec=User, id=123456789)
    update.effective_chat = MagicMock(spec=Chat, id=123456789)
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.user_data = {}
    return context


@pytest.fixture(autouse=True)
def mock_db():
    db = MagicMock(spec=Database)
    db.env = Environment.DEV
    db.get_user.return_value = None
    db.get_user_course.return_value = None
    with patch("src.bot.DB", db):
        yield db


@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    await start(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with(
        welcome_text(), do_quote=True
    )


@pytest.mark.asyncio
async def test_help_command(mock_update, mock_context):
    await help_command(mock_update, mock_context)
    mock_update.message.reply_markdown_v2.assert_called_once_with(
        HELP_MD, do_quote=True
    )


@pytest.mark.asyncio
async def test_about_command(mock_update, mock_context):
    await about(mock_update, mock_context)
    mock_update.message.reply_markdown_v2.assert_called_once_with(
        ABOUT_MD, do_quote=True
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
        MsgEnum.IS_SUBSCRIBED: True,
        MsgEnum.COLLEGE: "CAS",
        MsgEnum.DEPARTMENT: "CS",
        MsgEnum.COURSE_NUM: "111",
        MsgEnum.SECTION: "A1",
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
        MsgEnum.AWAITED_FIELD: MsgEnum.SECTION,
        MsgEnum.INVALID_MSG_ID: 123,
    }

    # Since we're not using callback_query, bot.send_message should be called
    mock_context.bot.send_message.return_value = "Aborted."

    result = await cancel(mock_update, mock_context)

    # Verify results
    assert result == ConversationHandler.END
    assert MsgEnum.AWAITED_FIELD not in mock_context.user_data
    assert MsgEnum.INVALID_MSG_ID not in mock_context.user_data
    mock_context.bot.send_message.assert_called_once_with(123456789, "Aborted.")


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

    # Check that there's at least one button in the markup
    keyboard = mock_update.message.reply_text.call_args[1][
        "reply_markup"
    ].inline_keyboard
    assert len(keyboard) > 0


@pytest.mark.asyncio
async def test_unknown_command(mock_update, mock_context):
    from src.bot import unknown

    await unknown(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with(
        UNKNOWN_CMD_TEXT, do_quote=True
    )


@pytest.mark.asyncio
async def test_feedback_flow(mock_update, mock_context):
    # Test feedback initiation
    result = await await_feedback(mock_update, mock_context)
    assert result == InputStates.AWAIT_FEEDBACK
    mock_update.message.reply_text.assert_called_once_with(
        FEEDBACK_TEXT, do_quote=True, reply_markup=ForceReply()
    )

    mock_update.message.reply_text.reset_mock()

    # Test feedback submission
    mock_update.message.text = "Test feedback"
    mock_context.bot.send_message.return_value = AsyncMock()
    result = await save_feedback(mock_update, mock_context)

    assert result == ConversationHandler.END
    mock_context.bot.send_message.assert_called_once()
    mock_update.message.reply_text.assert_called_once_with(FEEDBACK_SUCCESS_TEXT)


@pytest.mark.asyncio
async def test_save_custom_input_uses_awaited_field(mock_update, mock_context):
    # "AA" looks like a department, but the user was asked for a section
    mock_context.user_data = {
        MsgEnum.AWAITED_FIELD: MsgEnum.SECTION,
        MsgEnum.PROMPT_MSG_ID: 1,
        MsgEnum.SUBSCRIPTION_MSG_ID: 2,
    }
    mock_update.message.text = "aa"

    result = await save_custom_input(mock_update, mock_context)

    assert result == InputStates.AWAIT_SELECTION
    assert mock_context.user_data[MsgEnum.SECTION] == "AA"
    assert MsgEnum.DEPARTMENT not in mock_context.user_data
    mock_context.bot.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_save_custom_input_rejects_invalid(mock_update, mock_context):
    mock_context.user_data = {
        MsgEnum.AWAITED_FIELD: MsgEnum.COURSE_NUM,
        MsgEnum.PROMPT_MSG_ID: 1,
    }
    mock_update.message.text = "abc"
    mock_update.message.reply_text.return_value = MagicMock(message_id=3)

    await save_custom_input(mock_update, mock_context)

    assert MsgEnum.COURSE_NUM not in mock_context.user_data
    assert mock_context.user_data[MsgEnum.INVALID_MSG_ID] == 3
    mock_context.bot.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_error_handler_truncates_long_traceback(mock_update, mock_context):
    try:
        raise ValueError("<" * 10_000)
    except ValueError as e:
        mock_context.error = e
    await error_handler(mock_update, mock_context)

    text = mock_context.bot.send_message.call_args.kwargs["text"]
    assert len(text) <= 4096
    assert text.endswith("</pre>")


@pytest.mark.asyncio
async def test_error_handler_ignores_polling_conflict(mock_update, mock_context):
    mock_context.error = Conflict("terminated by other getUpdates request")
    await error_handler(mock_update, mock_context)
    mock_context.bot.send_message.assert_not_called()
