import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import cast
from telegram import (Update, InlineKeyboardMarkup,
                      ForceReply, Message, constants)
from telegram.ext import (filters, ApplicationBuilder, CommandHandler,
                          ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler)

import conv
import db
from course import Course

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))

(
    AWAIT_SELECTION,
    AWAIT_CUSTOM_INPUT,
    INPUT_COLLEGE,
    INPUT_DEPARTMENT,
    INPUT_COURSE_NUM,
    INPUT_SECTION,
    SUBMIT,
    CANCEL
) = map(chr, range(8))

(
    COLLEGE,
    DEPARTMENT,
    COURSE_NUM,
    SECTION,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED,
    SUBSCRIPTION_MSG_ID,
    PROMPT_MSG_ID
) = map(chr, range(8))

"""Helper functions"""


def handle_subscription(user_cache, user_course: dict[str, str] | None):
    """Updates user cache with course information and return subscription status"""
    if user_course is None:
        return False

    college, dep_num, section = user_course["name"].split()
    department, number = dep_num[:2], dep_num[2:]

    user_cache[COLLEGE] = college
    user_cache[DEPARTMENT] = department
    user_cache[COURSE_NUM] = number
    user_cache[SECTION] = section

    return True


def get_subscription_status(user_cache: dict, context: ContextTypes.DEFAULT_TYPE):
    """Check user subscription and updates cache"""
    user_id = str(context._user_id)

    if user_cache.get(IS_SUBSCRIBED) is None:
        user_course = db.find_user_course(user_id)
        user_cache[IS_SUBSCRIBED] = handle_subscription(
            user_cache, user_course)

    if user_cache.get(LAST_SUBSCRIBED) is None:
        user = db.find_user(user_id)
        user_cache[LAST_SUBSCRIBED] = user["last_subscribed"] if user else None

    return user_cache[IS_SUBSCRIBED], user_cache[LAST_SUBSCRIBED]


"""Conversation callbacks"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(conv.WELCOME_TEXT)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_cache = cast(dict, context.user_data)
    is_subscribed, last_subscribed = get_subscription_status(
        user_cache, context)
    last_subscribed = cast(datetime, last_subscribed)

    # Check user constraints (subscription status and time)
    if is_subscribed:
        course_name = conv.get_course_name(user_cache)
        text = (f"*You are already subscribed to {course_name}*\!\n\n"
                "Use /unsubscribe to remove your subscription\."
                )
        await update.message.reply_markdown_v2(text)
        return ConversationHandler.END

    if last_subscribed:
        next_subscribed = last_subscribed + \
            timedelta(hours=Course.REFRESH_TIME_HOURS)
        next_subscribed = next_subscribed.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < next_subscribed:
            next_subscribed_local = next_subscribed.astimezone(
                ZoneInfo("America/New_York")).strftime("%b %d %I:%M%p %Z")
            text = ("*You have recently subscribed to a course*\.\n\n"
                    f"Please wait until {next_subscribed_local} to subscribe\."
                    )
            await update.message.reply_markdown_v2(text)
            return ConversationHandler.END

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)
    subscription_text = conv.get_subscription_text(user_cache)
    conv_message = await update.message.reply_markdown_v2(subscription_text, reply_markup=keyboard)
    user_cache[SUBSCRIPTION_MSG_ID] = conv_message.message_id

    return AWAIT_SELECTION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    for key in (COLLEGE, DEPARTMENT, COURSE_NUM, SECTION):
        context.user_data.pop(key, None)
    query = update.callback_query
    # handle function entries: callback or command
    if query:
        await query.answer()
        await cast(Message, update.effective_message).edit_text("Transaction cancelled.")
    else:
        await context.bot.send_message(context._chat_id, "Transaction cancelled.")

    return ConversationHandler.END


async def handle_college_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = conv.get_college_buttons()
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def handle_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup()

    keyword = ""
    if query.data == INPUT_DEPARTMENT:
        keyword = "department"
    elif query.data == INPUT_COURSE_NUM:
        keyword = "course number"
    elif query.data == INPUT_SECTION:
        keyword = "section"

    prompt = await context.bot.send_message(context._chat_id, f"State the {keyword}", reply_markup=ForceReply())
    context.user_data[PROMPT_MSG_ID] = prompt.message_id
    return AWAIT_CUSTOM_INPUT


async def save_college_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for chosen college"""
    query = update.callback_query
    await query.answer()
    
    user_cache = cast(dict, context.user_data)
    user_cache[COLLEGE] = query.data

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)
    subscription_text = conv.get_subscription_text(user_cache)
    await update.callback_query.edit_message_text(text=subscription_text,
                                                  parse_mode=constants.ParseMode.MARKDOWN_V2,
                                                  reply_markup=keyboard)

    return AWAIT_SELECTION


async def save_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for custom inputs"""
    message = update.message
    user_cache = cast(dict, context.user_data)
    reply = message.text.upper()
    await message.delete()
    await context.bot.delete_message(context._chat_id, context.user_data[PROMPT_MSG_ID])

    if re.fullmatch("^[A-Z]{2}$", reply):
        user_cache[DEPARTMENT] = reply
    elif re.fullmatch("^[1-9]{1}[0-9]{2}$", reply):
        user_cache[COURSE_NUM] = reply
    elif re.fullmatch("^[A-Z]{1}[A-Z1-9]{1}$", reply):
        user_cache[SECTION] = reply
    else:
        await message.reply_text("Invalid input. Please try again.")

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)
    subscription_text = conv.get_subscription_text(user_cache)
    await context.bot.edit_message_text(text=subscription_text,
                                        chat_id=context._chat_id,
                                        message_id=user_cache[SUBSCRIPTION_MSG_ID],
                                        parse_mode=constants.ParseMode.MARKDOWN_V2,
                                        reply_markup=keyboard)
    return AWAIT_SELECTION


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit to database"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Submitting...")

    user_cache = cast(dict, context.user_data)
    course_name = conv.get_course_name(user_cache)
    user_id = str(context._user_id)
    db.update_db(course_name, user_id)
    curr_time = datetime.utcnow()
    db.update_user_subscription_time(user_id, curr_time)
    db.update_user_subscription_status(user_id, True)

    user_cache[IS_SUBSCRIBED] = True
    user_cache[LAST_SUBSCRIBED] = curr_time
    await cast(Message, update.effective_message).reply_text(f"You are now subscribed to {course_name}.")

    return ConversationHandler.END


async def unsubscribe_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_cache = cast(dict, context.user_data)
    is_subscribed, _ = get_subscription_status(user_cache, context)

    if is_subscribed:
        buttons = conv.get_unsubscribe_buttons()
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(conv.UNSUBSCRIBE_TEXT, reply_markup=keyboard)
        return AWAIT_SELECTION
    else:
        await update.message.reply_text(conv.NOT_SUBSCRIBED_TEXT)
        return ConversationHandler.END


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_cache = cast(dict, context.user_data)
    course_name = conv.get_course_name(user_cache)
    user_id = str(context._user_id)
    db.remove_user(course_name, user_id)
    db.update_user_subscription_status(user_id, False)
    for key in (COLLEGE, DEPARTMENT, COURSE_NUM, SECTION):
        user_cache.pop(key, None)
    user_cache[IS_SUBSCRIBED] = False

    await cast(Message, update._effective_message).edit_text(f"You have been unsubscribed from {course_name}.")
    return ConversationHandler.END


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown_v2(conv.HELP_TEXT)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown_v2(conv.ABOUT_TEXT)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(conv.UNKNOWN_CMD_TEXT)


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    selection_handlers = [
        CallbackQueryHandler(
            handle_college_input, pattern=f"^" + INPUT_COLLEGE + "$"),
        CallbackQueryHandler(
            handle_custom_input, pattern=f"^({INPUT_DEPARTMENT}|{INPUT_COURSE_NUM}|{INPUT_SECTION})$"),
        CallbackQueryHandler(submit, pattern="^" + SUBMIT + "$"),
    ]

    subscription_handler = ConversationHandler(
        entry_points=[CommandHandler("subscribe", subscribe)],
        states={
            AWAIT_SELECTION: selection_handlers,
            AWAIT_CUSTOM_INPUT: [MessageHandler(filters.REPLY, save_custom_input)],
        },
        fallbacks=[
            CallbackQueryHandler(save_college_input, pattern="^[A-Z]{3}$"),
            CallbackQueryHandler(cancel, pattern="^" + CANCEL + "$"),
            CommandHandler("cancel", cancel)
        ],
    )
    unsubscribe_handler = ConversationHandler(
        entry_points=[CommandHandler(
            "unsubscribe", unsubscribe_dialog)],
        states={
            AWAIT_SELECTION: [CallbackQueryHandler(
                unsubscribe, pattern="^" + SUBMIT + "$")]
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^" + CANCEL + "$"),
            CommandHandler("cancel", cancel)
        ],
    )
    application.add_handler(subscription_handler)
    application.add_handler(unsubscribe_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("about", about))

    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    application.add_handler(unknown_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
