from __future__ import annotations

import html
import logging
import os
import traceback
from typing import Any, cast

import pendulum
from dotenv import load_dotenv
from telegram import (
    ForceReply,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.db import Database
from src.finder import Finder
from src.search import BUClassSearch
from utils import conv
from utils.constants import (
    COURSE_NAME,
    FORM_FIELDS,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED,
    LAST_SUBSCRIPTION,
    Environment,
    InputStates,
    TimeConstants,
)
from utils.constants import (
    Message as MsgEnum,
)
from utils.models import Course

# Type alias for better readability
type UserCache = dict[str, Any]

# Initialize DB at module level
DB: Database | None = None

load_dotenv()
FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
FINDER_INTERVAL_SECONDS = 60
MESSAGE_LEN_LIMIT = 4096

INPUT_FIELDS = {
    InputStates.INPUT_DEPARTMENT: MsgEnum.DEPARTMENT,
    InputStates.INPUT_COURSE_NUM: MsgEnum.COURSE_NUM,
    InputStates.INPUT_SECTION: MsgEnum.SECTION,
}

logger = logging.getLogger(__name__)


# Conversation helpers


def get_subscription_status(
    user_cache: UserCache, update: Update
) -> tuple[bool, pendulum.DateTime | None]:
    """Check user subscription and update cache"""
    user_id = str(update.effective_user.id)
    user = DB.get_user(user_id)

    user_cache[MsgEnum.IS_SUBSCRIBED] = user[IS_SUBSCRIBED] if user else False
    user_cache[MsgEnum.LAST_SUBSCRIBED] = (
        pendulum.instance(user[LAST_SUBSCRIBED]) if user else None
    )
    user_cache[MsgEnum.LAST_SUBSCRIPTION] = user[LAST_SUBSCRIPTION] if user else ""

    if not user_cache[MsgEnum.IS_SUBSCRIBED]:
        for key in FORM_FIELDS:
            user_cache.pop(key, None)
    elif not all(field in user_cache for field in FORM_FIELDS):
        user_course = DB.get_user_course(user_id)
        populate_cache(user_cache, user_course)

    return user_cache[MsgEnum.IS_SUBSCRIBED], user_cache[MsgEnum.LAST_SUBSCRIBED]


def populate_cache(user_cache: UserCache, user_course: dict[str, str]):
    """Update user cache with course information"""
    course = Course.parse(user_course[COURSE_NAME])
    user_cache[MsgEnum.COLLEGE] = course.college
    user_cache[MsgEnum.DEPARTMENT] = course.department
    user_cache[MsgEnum.COURSE_NUM] = course.number
    user_cache[MsgEnum.SECTION] = course.section


async def clear_invalid_msg(
    user_cache: UserCache, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if MsgEnum.INVALID_MSG_ID in user_cache:
        await context.bot.delete_message(
            update.effective_chat.id, user_cache.pop(MsgEnum.INVALID_MSG_ID)
        )


# Conversation callbacks


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/start` command"""
    await update.message.reply_text(conv.welcome_text(), do_quote=True)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the conversation and asks the user about their subscription"""
    user_cache = cast(UserCache, context.user_data)
    is_subscribed, last_subscribed = get_subscription_status(user_cache, update)

    # Check user constraints (subscription status and time)
    if is_subscribed:
        course = conv.get_course(user_cache)
        await update.message.reply_markdown_v2(
            conv.already_subscribed_md(course), do_quote=True
        )
        return ConversationHandler.END

    if DB.env == Environment.PROD and last_subscribed:
        next_subscribed = last_subscribed.add(hours=TimeConstants.REFRESH_TIME_HOURS)
        if pendulum.now() < next_subscribed:
            next_subscribed_local = next_subscribed.in_timezone(
                "America/New_York"
            ).strftime("%b %d %I:%M%p %Z")
            await update.message.reply_markdown_v2(
                conv.recently_subscribed_md(next_subscribed_local), do_quote=True
            )
            return ConversationHandler.END

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)
    conv_message = await update.message.reply_markdown_v2(
        text=conv.get_subscription_md(user_cache), do_quote=True, reply_markup=keyboard
    )
    user_cache[MsgEnum.SUBSCRIPTION_MSG_ID] = conv_message.message_id

    return InputStates.AWAIT_SELECTION


async def await_college_input(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Ask user for college input"""
    query = update.callback_query
    await query.answer()

    buttons = conv.get_college_buttons()
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def save_college_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for chosen college"""
    query = update.callback_query
    await query.answer()

    user_cache = cast(UserCache, context.user_data)
    user_cache[MsgEnum.COLLEGE] = query.data

    await query.edit_message_text(
        text=conv.get_subscription_md(user_cache),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(conv.get_main_buttons(user_cache)),
    )
    return InputStates.AWAIT_SELECTION


async def await_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for the department, course number or section"""
    query = update.callback_query
    await query.answer()
    user_cache = cast(UserCache, context.user_data)
    await clear_invalid_msg(user_cache, update, context)

    field = INPUT_FIELDS[InputStates(int(query.data))]
    user_cache[MsgEnum.AWAITED_FIELD] = field

    prompt = await context.bot.send_message(
        update.effective_chat.id,
        f"State the {conv.FIELD_LABELS[field]}",
        reply_markup=ForceReply(),
    )
    user_cache[MsgEnum.PROMPT_MSG_ID] = prompt.message_id
    return InputStates.AWAIT_CUSTOM_INPUT


async def save_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validate the reply against the field that was asked for and update cache"""
    message = update.message
    await message.delete()

    user_cache = cast(UserCache, context.user_data)
    prompt_msg_id = user_cache.get(MsgEnum.PROMPT_MSG_ID, None)
    assert prompt_msg_id, "Prompt message ID not found"
    await context.bot.delete_message(update.effective_chat.id, prompt_msg_id)

    field = user_cache.pop(MsgEnum.AWAITED_FIELD, None)
    assert field, "Awaited field not found"
    user_cache_snapshot = user_cache.copy()

    if value := conv.parse_field(field, message.text):
        user_cache[field] = value
    else:
        msg = await message.reply_text(
            f"Invalid {conv.FIELD_LABELS[field]}. Please try again."
        )
        user_cache[MsgEnum.INVALID_MSG_ID] = msg.message_id

    if not conv.fields_equal(user_cache, user_cache_snapshot, FORM_FIELDS):
        sub_msg_id = user_cache.get(MsgEnum.SUBSCRIPTION_MSG_ID, None)
        assert sub_msg_id, "Subscription message ID not found"
        await context.bot.edit_message_text(
            text=conv.get_subscription_md(user_cache),
            chat_id=update.effective_chat.id,
            message_id=sub_msg_id,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(conv.get_main_buttons(user_cache)),
        )
    return InputStates.AWAIT_SELECTION


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save subscription to database"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Submitting...")

    user_cache = cast(UserCache, context.user_data)
    course = conv.get_course(user_cache)
    user_id = str(update.effective_user.id)
    curr_time = pendulum.now()
    DB.subscribe(course, user_id, curr_time)

    user_cache[MsgEnum.IS_SUBSCRIBED] = True
    user_cache[MsgEnum.LAST_SUBSCRIBED] = curr_time
    await update.effective_message.reply_text(f"You are now subscribed to {course}.")
    return ConversationHandler.END


async def resubscribe_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for confirmation to resubscribe"""
    user_cache = cast(UserCache, context.user_data)
    is_subscribed, _ = get_subscription_status(user_cache, update)
    if is_subscribed:
        course = conv.get_course(user_cache)
        await update.message.reply_markdown_v2(
            conv.already_subscribed_md(course), do_quote=True
        )
        return ConversationHandler.END

    last_subscribed_course = user_cache.get(MsgEnum.LAST_SUBSCRIPTION, "")
    if last_subscribed_course == "":
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT, do_quote=True)
        return ConversationHandler.END

    text = f"Confirm resubscription to {last_subscribed_course}?"
    await update.message.reply_text(
        text=text,
        do_quote=True,
        reply_markup=InlineKeyboardMarkup(conv.get_confirmation_buttons()),
    )
    return InputStates.AWAIT_SELECTION


async def resubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resubscribe user to course"""
    query = update.callback_query
    await query.answer()

    user_cache = cast(UserCache, context.user_data)
    last_subscribed_course_str = user_cache.get(MsgEnum.LAST_SUBSCRIPTION, "")
    assert last_subscribed_course_str, "Last subscribed course not found"

    last_subscribed_course = Course.parse(last_subscribed_course_str)
    user_id = str(update.effective_user.id)
    curr_time = pendulum.now()
    DB.subscribe(last_subscribed_course, user_id, curr_time)

    user_cache[MsgEnum.IS_SUBSCRIBED] = True
    user_cache[MsgEnum.LAST_SUBSCRIBED] = curr_time
    await update.effective_message.edit_text(
        f"Successfully resubscribed to {last_subscribed_course}."
    )
    return ConversationHandler.END


async def unsubscribe_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for confirmation to unsubscribe"""
    is_subscribed, _ = get_subscription_status(context.user_data, update)
    if is_subscribed:
        buttons = conv.get_confirmation_buttons()
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            conv.UNSUBSCRIBE_TEXT, do_quote=True, reply_markup=keyboard
        )
        return InputStates.AWAIT_SELECTION
    else:
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT, do_quote=True)
        return ConversationHandler.END


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe user from course"""
    query = update.callback_query
    await query.answer()

    user_cache = cast(UserCache, context.user_data)
    course = conv.get_course(user_cache)
    user_id = str(update.effective_user.id)
    DB.unsubscribe(course, user_id)

    for key in FORM_FIELDS:
        user_cache.pop(key, None)
    user_cache[MsgEnum.IS_SUBSCRIBED] = False

    await update.effective_message.edit_text(
        f"You have been unsubscribed from {course}."
    )
    return ConversationHandler.END


async def await_feedback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Ask user for feedback"""
    await update.message.reply_text(
        conv.FEEDBACK_TEXT, do_quote=True, reply_markup=ForceReply()
    )
    return InputStates.AWAIT_FEEDBACK


async def save_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirect feedback to feedback channel"""
    feedback = update.message.text
    try:
        await context.bot.send_message(
            chat_id=FEEDBACK_CHANNEL_ID, text=f"Feedback: {feedback}"
        )
    except TelegramError:
        logger.exception("Failed to forward feedback")
        await update.message.reply_text(conv.FEEDBACK_FAILURE_TEXT)
    else:
        await update.message.reply_text(conv.FEEDBACK_SUCCESS_TEXT)
    return ConversationHandler.END


async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/help` command"""
    await update.message.reply_markdown_v2(conv.HELP_MD, do_quote=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    await clear_invalid_msg(context.user_data, update, context)
    context.user_data.pop(MsgEnum.AWAITED_FIELD, None)

    abort_msg = "Aborted."
    if query := update.callback_query:
        await query.answer()
        await update.effective_message.edit_text(abort_msg)
    else:
        await context.bot.send_message(update.effective_chat.id, abort_msg)
    return ConversationHandler.END


async def about(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/about` command"""
    await update.message.reply_markdown_v2(conv.ABOUT_MD, do_quote=True)


async def unknown(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(conv.UNKNOWN_CMD_TEXT, do_quote=True)


async def error_handler(_update: object, context: ContextTypes.DEFAULT_TYPE):
    """Send an error notification to Telegram feedback channel."""
    if isinstance(context.error, Conflict):
        # Two dev pollers share a token (e.g. a local run and CI's smoke test).
        # Polling retries and takes over once the other one stops.
        logger.warning("Another instance is polling: %s", context.error)
        return
    logger.error("Unhandled exception", exc_info=context.error)
    tb_string = "".join(
        traceback.format_exception(None, context.error, context.error.__traceback__)
    )
    template = "An exception was raised while handling an update\n<pre>{tb}</pre>"
    # Keep the tail of the traceback, where the error is, within Telegram's limit
    budget = MESSAGE_LEN_LIMIT - len(template)
    tb_html = html.escape(tb_string)
    while len(tb_html) > budget:
        tb_string = tb_string[len(tb_html) - budget :]
        tb_html = html.escape(tb_string)
    await context.bot.send_message(
        chat_id=FEEDBACK_CHANNEL_ID,
        text=template.format(tb=tb_html),
        parse_mode=constants.ParseMode.HTML,
    )


def create_conversation_handlers() -> list[ConversationHandler]:
    """Create all conversation handlers for the bot"""
    subscription_pattern = f"^({InputStates.INPUT_DEPARTMENT}|{InputStates.INPUT_COURSE_NUM}|{InputStates.INPUT_SECTION})$"

    subscription_sel_handlers = [
        CallbackQueryHandler(await_college_input, f"^{InputStates.INPUT_COLLEGE}$"),
        CallbackQueryHandler(await_custom_input, subscription_pattern),
        CallbackQueryHandler(submit, f"^{InputStates.SUBMIT}$"),
    ]

    handlers = [
        ConversationHandler(
            entry_points=[CommandHandler("subscribe", subscribe)],
            states={
                InputStates.AWAIT_SELECTION: subscription_sel_handlers,
                InputStates.AWAIT_CUSTOM_INPUT: [
                    MessageHandler(filters.TEXT & filters.REPLY, save_custom_input)
                ],
            },
            fallbacks=[
                CallbackQueryHandler(save_college_input, "^[A-Z]{3}$"),
                CallbackQueryHandler(cancel, f"^{InputStates.CANCEL}$"),
                CommandHandler("cancel", cancel),
            ],
        ),
        ConversationHandler(
            entry_points=[CommandHandler("resubscribe", resubscribe_dialog)],
            states={
                InputStates.AWAIT_SELECTION: [
                    CallbackQueryHandler(resubscribe, f"^{InputStates.PROCEED}$")
                ],
            },
            fallbacks=[
                CallbackQueryHandler(cancel, f"^{InputStates.CANCEL}$"),
                CommandHandler("cancel", cancel),
            ],
        ),
        ConversationHandler(
            entry_points=[CommandHandler("unsubscribe", unsubscribe_dialog)],
            states={
                InputStates.AWAIT_SELECTION: [
                    CallbackQueryHandler(unsubscribe, f"^{InputStates.PROCEED}$")
                ]
            },
            fallbacks=[
                CallbackQueryHandler(cancel, f"^{InputStates.CANCEL}$"),
                CommandHandler("cancel", cancel),
            ],
        ),
        ConversationHandler(
            entry_points=[CommandHandler("feedback", await_feedback)],
            states={
                InputStates.AWAIT_FEEDBACK: [
                    MessageHandler(filters.TEXT & filters.REPLY, save_feedback)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        ),
    ]
    return handlers


def build_application(env: Environment) -> Application:
    """Build the bot with its handlers and the finder job. The caller runs it."""
    global DB

    if not DB:
        DB = Database(env)

    bot_token = os.getenv(
        "TELEGRAM_TOKEN" if env == Environment.PROD else "TEST_TELEGRAM_TOKEN"
    )
    application = ApplicationBuilder().token(bot_token).build()

    # Add conversation handlers
    for handler in create_conversation_handlers():
        application.add_handler(handler)

    # Add command handlers
    for command, callback in [
        ("start", start),
        ("help", help_command),
        ("about", about),
    ]:
        application.add_handler(CommandHandler(command, callback))

    # Add fallback handlers
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.add_error_handler(error_handler)

    # Schedule the finder; the job queue starts with the application
    finder = Finder(DB, BUClassSearch(), application.bot, FEEDBACK_CHANNEL_ID)
    application.job_queue.run_repeating(
        callback=finder.run, interval=FINDER_INTERVAL_SECONDS
    )

    return application
