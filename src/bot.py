import os
import sys
import re
import html
import traceback
import pendulum
from typing import cast
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, ForceReply, Message, constants, error
from telegram.ext import (
    filters,
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import finder
from utils.constants import *
from utils import conv
from utils.db import Database

load_dotenv()

FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))


# Conversation helpers


def get_subscription_status(
    user_cache: dict, context: ContextTypes.DEFAULT_TYPE
) -> tuple[bool, pendulum.DateTime | None]:
    """Check user subscription and update cache"""
    user_id = str(context._user_id)
    user = DB.get_user(user_id)

    user_cache[Message.IS_SUBSCRIBED] = user["is_subscribed"] if user else False
    user_cache[Message.LAST_SUBSCRIBED] = (
        pendulum.instance(user["last_subscribed"]) if user else None
    )
    user_cache[Message.LAST_SUBSCRIPTION] = user["last_subscription"] if user else ""

    if not user_cache[Message.IS_SUBSCRIBED]:
        for key in FORM_FIELDS:
            user_cache.pop(key, None)
    elif not all(field in user_cache for field in FORM_FIELDS):
        user_course = DB.get_user_course(user_id)
        populate_cache(user_cache, user_course)

    return user_cache[Message.IS_SUBSCRIBED], user_cache[Message.LAST_SUBSCRIBED]


def populate_cache(user_cache: dict, user_course: dict[str, str]):
    """Update user cache with course information"""
    college, dep_num, section = user_course["name"].split()
    department, number = dep_num[:2], dep_num[2:]

    user_cache[Message.COLLEGE] = college
    user_cache[Message.DEPARTMENT] = department
    user_cache[Message.COURSE_NUM] = number
    user_cache[Message.SECTION] = section


async def clear_invalid_msg(user_cache: dict, context: ContextTypes.DEFAULT_TYPE):
    if Message.INVALID_MSG_ID in user_cache:
        await context.bot.delete_message(
            context._chat_id, user_cache[Message.INVALID_MSG_ID]
        )
        user_cache.pop(Message.INVALID_MSG_ID)


# Conversation callbacks


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/start` command"""
    await update.message.reply_text(conv.WELCOME_TEXT, quote=True)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the conversation and asks the user about their subscription"""
    user_cache = cast(dict, context.user_data)
    is_subscribed, last_subscribed = get_subscription_status(user_cache, context)

    # Check user constraints (subscription status and time)
    if is_subscribed:
        course_name = conv.get_course_name(user_cache)
        await update.message.reply_markdown_v2(
            conv.already_subscribed_md(course_name), quote=True
        )
        return ConversationHandler.END

    if DB.env == Environment.PROD and last_subscribed:
        next_subscribed = last_subscribed.add(hours=TimeConstants.REFRESH_TIME_HOURS)
        if pendulum.now() < next_subscribed:
            next_subscribed_local = next_subscribed.in_timezone(
                "America/New_York"
            ).strftime("%b %d %I:%M%p %Z")
            await update.message.reply_markdown_v2(
                conv.recently_subscribed_md(next_subscribed_local), quote=True
            )
            return ConversationHandler.END

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)
    conv_message = await update.message.reply_markdown_v2(
        text=conv.get_subscription_md(user_cache), quote=True, reply_markup=keyboard
    )
    user_cache[Message.SUBSCRIPTION_MSG_ID] = conv_message.message_id

    return InputStates.AWAIT_SELECTION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    await clear_invalid_msg(context.user_data, context)
    for key in CRED_FIELDS:
        context.user_data.pop(key, None)

    abort_msg = "Transaction aborted."
    if query := update.callback_query:
        await query.answer()
        await cast(Message, update.effective_message).edit_text(abort_msg)
    else:
        await context.bot.send_message(context._chat_id, abort_msg)
    return ConversationHandler.END


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

    user_cache = cast(dict, context.user_data)
    user_cache[Message.COLLEGE] = query.data

    await query.edit_message_text(
        text=conv.get_subscription_md(user_cache),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(conv.get_main_buttons(user_cache)),
    )
    return InputStates.AWAIT_SELECTION


async def await_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for custom input"""
    query = update.callback_query
    await query.answer()
    user_cache = cast(dict, context.user_data)
    await clear_invalid_msg(user_cache, context)

    keyword = ""
    if query.data == InputStates.INPUT_DEPARTMENT:
        keyword = "department"
    elif query.data == InputStates.INPUT_COURSE_NUM:
        keyword = "course number"
    elif query.data == InputStates.INPUT_SECTION:
        keyword = "section"

    prompt = await context.bot.send_message(
        context._chat_id, f"State the {keyword}", reply_markup=ForceReply()
    )
    user_cache[Message.PROMPT_MSG_ID] = prompt.message_id
    return InputStates.AWAIT_CUSTOM_INPUT


async def save_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for custom inputs"""
    message = update.message
    await message.delete()

    user_cache = cast(dict, context.user_data)
    prompt_msg_id = user_cache.get(Message.PROMPT_MSG_ID, None)
    assert prompt_msg_id, "Prompt message ID not found"
    await context.bot.delete_message(context._chat_id, prompt_msg_id)

    user_cache_snapshot = user_cache.copy()

    reply = message.text.upper()
    if re.fullmatch("^[A-Z]{2}$", reply):
        user_cache[Message.DEPARTMENT] = reply
    elif re.fullmatch("^[1-9]{1}[0-9]{2}$", reply):
        user_cache[Message.COURSE_NUM] = reply
    elif re.fullmatch("^[A-Z]{1}[A-Z1-9]{1}$", reply):
        user_cache[Message.SECTION] = reply
    else:
        msg = await message.reply_text("Invalid input. Please try again.")
        user_cache[Message.INVALID_MSG_ID] = msg.message_id

    if not conv.fields_equal(user_cache, user_cache_snapshot, FORM_FIELDS):
        sub_msg_id = user_cache.get(Message.SUBSCRIPTION_MSG_ID, None)
        assert sub_msg_id, "Subscription message ID not found"
        await context.bot.edit_message_text(
            text=conv.get_subscription_md(user_cache),
            chat_id=context._chat_id,
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

    user_cache = cast(dict, context.user_data)
    course_name = conv.get_course_name(user_cache)
    user_id = str(context._user_id)
    curr_time = pendulum.now()
    DB.subscribe(course_name, user_id, curr_time)

    user_cache[Message.IS_SUBSCRIBED] = True
    user_cache[Message.LAST_SUBSCRIBED] = curr_time
    await cast(Message, update.effective_message).reply_text(
        f"You are now subscribed to {course_name}."
    )
    return ConversationHandler.END


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for confirmation to register"""
    user_cache = cast(dict, context.user_data)
    is_subscribed, last_subscribed = get_subscription_status(user_cache, context)

    if last_subscribed is None:
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT, quote=True)
        return ConversationHandler.END

    if is_subscribed:
        await update.message.reply_text(conv.NOT_AVAILABLE_TEXT, quote=True)
        return ConversationHandler.END

    last_subscribed_course = user_cache.get(Message.LAST_SUBSCRIPTION, "")
    assert last_subscribed_course, "Last subscribed course not found"
    reg_prompt = f"Register for {last_subscribed_course}?"
    await update.message.reply_text(
        text=reg_prompt,
        quote=True,
        reply_markup=InlineKeyboardMarkup(conv.get_confirmation_buttons()),
    )
    return InputStates.AWAIT_SELECTION


async def update_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_cache = cast(dict, context.user_data)
    cred_text = conv.get_cred_text(user_cache)
    reply_markup = InlineKeyboardMarkup(conv.get_cred_buttons(user_cache))
    if query := update.callback_query:
        await query.answer()
        conv_message = await query.edit_message_text(
            text=cred_text,
            reply_markup=reply_markup,
        )
    else:
        cred_msg_id = user_cache.get(Message.CRED_MSG_ID, None)
        assert cred_msg_id, "Credential message ID not found"
        conv_message = await context.bot.edit_message_text(
            text=cred_text,
            chat_id=context._chat_id,
            message_id=cred_msg_id,
            reply_markup=reply_markup,
        )
    user_cache[Message.CRED_MSG_ID] = conv_message.message_id
    return InputStates.AWAIT_SELECTION


async def request_username_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ask_credential(update, context, Message.USERNAME)
    return InputStates.INPUT_USERNAME


async def request_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ask_credential(update, context, Message.PASSWORD)
    return InputStates.INPUT_PASSWORD


async def ask_credential(
    update: Update, context: ContextTypes.DEFAULT_TYPE, credential: str
):
    await update.callback_query.answer()
    user_cache = cast(dict, context.user_data)
    await clear_invalid_msg(user_cache, context)
    credential = "password" if credential == Message.PASSWORD else "username"
    prompt = await context.bot.send_message(
        context._chat_id, f"State your {credential}", reply_markup=ForceReply()
    )
    user_cache[Message.PROMPT_MSG_ID] = prompt.message_id


async def save_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_credential(update, context, Message.USERNAME)
    return InputStates.AWAIT_SELECTION


async def save_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_credential(update, context, Message.PASSWORD)
    return InputStates.AWAIT_SELECTION


async def save_credential(
    update: Update, context: ContextTypes.DEFAULT_TYPE, credential: str
):
    message = update.message
    user_cache = cast(dict, context.user_data)
    user_cache_snapshot = user_cache.copy()
    user_cache[credential] = message.text
    await message.delete()
    await context.bot.delete_message(
        context._chat_id, user_cache[Message.PROMPT_MSG_ID]
    )

    new_text = conv.get_cred_text(user_cache)
    old_text = conv.get_cred_text(user_cache_snapshot)
    if new_text != old_text:
        cred_msg_id = user_cache.get(Message.CRED_MSG_ID, None)
        assert cred_msg_id, "Credential message ID not found"
        await context.bot.edit_message_text(
            text=new_text,
            chat_id=context._chat_id,
            message_id=cred_msg_id,
            reply_markup=InlineKeyboardMarkup(conv.get_cred_buttons(user_cache)),
        )


async def start_webdriver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_cache = cast(dict, context.user_data)
    try:
        await query.edit_message_text("Establishing connection...")
        await finder.register_course(DB.env, user_cache, query)
    except ValueError:
        return await update_credentials(update, context)
    except Exception as e:
        await query.edit_message_text(
            text="An unexpected error occurred. Please try again later."
        )
        raise e
    for key in CRED_FIELDS:
        user_cache.pop(key, None)
    return ConversationHandler.END


async def resubscribe_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for confirmation to resubscribe"""
    user_cache = cast(dict, context.user_data)
    is_subscribed, _ = get_subscription_status(user_cache, context)
    if is_subscribed:
        course_name = conv.get_course_name(user_cache)
        await update.message.reply_markdown_v2(
            conv.already_subscribed_md(course_name), quote=True
        )
        return ConversationHandler.END

    last_subscribed_course = user_cache.get(Message.LAST_SUBSCRIPTION, "")
    if last_subscribed_course == "":
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT, quote=True)
        return ConversationHandler.END

    text = f"Confirm resubscription to {last_subscribed_course}?"
    await update.message.reply_text(
        text=text,
        quote=True,
        reply_markup=InlineKeyboardMarkup(conv.get_confirmation_buttons()),
    )
    return InputStates.AWAIT_SELECTION


async def resubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resubscribe user to course"""
    query = update.callback_query
    await query.answer()

    user_cache = cast(dict, context.user_data)
    last_subscribed_course = user_cache.get(Message.LAST_SUBSCRIPTION, "")
    assert last_subscribed_course, "Last subscribed course not found"
    user_id = str(context._user_id)
    curr_time = pendulum.now()
    DB.subscribe(last_subscribed_course, user_id, curr_time)

    user_cache[Message.IS_SUBSCRIBED] = True
    user_cache[Message.LAST_SUBSCRIBED] = curr_time
    await cast(Message, update.effective_message).edit_text(
        f"Successfully resubscribed to {last_subscribed_course}."
    )
    return ConversationHandler.END


async def unsubscribe_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for confirmation to unsubscribe"""
    is_subscribed, _ = get_subscription_status(context.user_data, context)
    if is_subscribed:
        buttons = conv.get_confirmation_buttons()
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            conv.UNSUBSCRIBE_TEXT, quote=True, reply_markup=keyboard
        )
        return InputStates.AWAIT_SELECTION
    else:
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT, quote=True)
        return ConversationHandler.END


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe user from course"""
    query = update.callback_query
    await query.answer()

    user_cache = cast(dict, context.user_data)
    course_name = conv.get_course_name(user_cache)
    user_id = str(context._user_id)
    DB.unsubscribe(course_name, user_id)

    for key in FORM_FIELDS:
        user_cache.pop(key, None)
    user_cache[Message.IS_SUBSCRIBED] = False

    await cast(Message, update._effective_message).edit_text(
        f"You have been unsubscribed from {course_name}."
    )
    return ConversationHandler.END


async def await_feedback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Ask user for feedback"""
    await update.message.reply_text(
        conv.FEEDBACK_TEXT, quote=True, reply_markup=ForceReply()
    )
    return InputStates.InputStates.AWAIT_FEEDBACK


async def save_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirect feedback to feedback channel"""
    feedback = update.message.text
    msg = await context.bot.send_message(
        chat_id=FEEDBACK_CHANNEL_ID, text=f"Feedback: {feedback}"
    )
    if msg:
        await update.message.reply_text(conv.FEEDBACK_SUCCESS_TEXT)
    else:
        await update.message.reply_text(conv.FEEDBACK_FAILURE_TEXT)
    return ConversationHandler.END


async def help(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/help` command"""
    await update.message.reply_markdown_v2(conv.HELP_MD, quote=True)


async def about(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle `/about` command"""
    await update.message.reply_markdown_v2(conv.ABOUT_MD, quote=True)


async def unknown(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(conv.UNKNOWN_CMD_TEXT, quote=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Send an error notification to Telegram feedback channel."""
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    if isinstance(context.error, error.Conflict):
        print(message)
    else:
        await context.bot.send_message(
            chat_id=FEEDBACK_CHANNEL_ID,
            text=message,
            parse_mode=constants.ParseMode.HTML,
        )


def main(env=Environment.PROD):
    print("Starting bot...")
    global DB

    DB = Database(env)
    bot_token = os.getenv(
        "TELEGRAM_TOKEN" if env == Environment.PROD else "TEST_TELEGRAM_TOKEN"
    )
    application: Application = ApplicationBuilder().token(bot_token).build()

    subscription_sel_handlers = [
        CallbackQueryHandler(
            await_college_input, pattern="^" + InputStates.INPUT_COLLEGE + "$"
        ),
        CallbackQueryHandler(
            await_custom_input,
            pattern=f"^({InputStates.INPUT_DEPARTMENT}|{InputStates.INPUT_COURSE_NUM}|{InputStates.INPUT_SECTION})$",
        ),
        CallbackQueryHandler(submit, pattern="^" + InputStates.SUBMIT + "$"),
    ]
    reg_sel_handlers = [
        CallbackQueryHandler(
            update_credentials, pattern="^" + InputStates.PROCEED + "$"
        ),
        CallbackQueryHandler(
            request_username_input, pattern="^" + InputStates.INPUT_USERNAME + "$"
        ),
        CallbackQueryHandler(
            request_password_input, pattern="^" + InputStates.INPUT_PASSWORD + "$"
        ),
        CallbackQueryHandler(start_webdriver, pattern="^" + InputStates.SUBMIT + "$"),
    ]

    subscription_handler = ConversationHandler(
        entry_points=[CommandHandler("subscribe", subscribe)],
        states={
            InputStates.AWAIT_SELECTION: subscription_sel_handlers,
            InputStates.AWAIT_CUSTOM_INPUT: [
                MessageHandler(filters.REPLY, save_custom_input)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(save_college_input, pattern="^[A-Z]{3}$"),
            CallbackQueryHandler(cancel, pattern="^" + InputStates.CANCEL + "$"),
            CommandHandler("cancel", cancel),
        ],
    )
    register_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register)],
        states={
            InputStates.AWAIT_SELECTION: reg_sel_handlers,
            InputStates.AWAIT_InputStates.INPUT_USERNAME: [
                MessageHandler(filters.REPLY, save_username)
            ],
            InputStates.AWAIT_InputStates.INPUT_PASSWORD: [
                MessageHandler(filters.REPLY, save_password)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^" + InputStates.CANCEL + "$"),
            CommandHandler("cancel", cancel),
        ],
    )
    resubscription_handler = ConversationHandler(
        entry_points=[CommandHandler("resubscribe", resubscribe_dialog)],
        states={
            InputStates.AWAIT_SELECTION: [
                CallbackQueryHandler(
                    resubscribe, pattern="^" + InputStates.PROCEED + "$"
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^" + InputStates.CANCEL + "$"),
            CommandHandler("cancel", cancel),
        ],
    )
    unsubscribe_handler = ConversationHandler(
        entry_points=[CommandHandler("unsubscribe", unsubscribe_dialog)],
        states={
            InputStates.AWAIT_SELECTION: [
                CallbackQueryHandler(
                    unsubscribe, pattern="^" + InputStates.PROCEED + "$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^" + InputStates.CANCEL + "$"),
            CommandHandler("cancel", cancel),
        ],
    )
    feedback_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", await_feedback)],
        states={
            InputStates.InputStates.AWAIT_FEEDBACK: [
                MessageHandler(filters.REPLY, save_feedback)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    unknown_handler = MessageHandler(filters.COMMAND, unknown)

    application.add_handler(subscription_handler)
    application.add_handler(register_handler)
    application.add_handler(resubscription_handler)
    application.add_handler(unsubscribe_handler)
    application.add_handler(feedback_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(unknown_handler)
    application.add_error_handler(error_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(callback=finder.run, interval=60, data={"db": DB})

    application.run_polling()


if __name__ == "__main__":
    main()
