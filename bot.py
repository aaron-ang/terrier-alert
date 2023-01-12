import os
import re
from datetime import datetime
from typing import cast
from telegram import (Update, InlineKeyboardMarkup, ForceReply, Message)
from telegram.ext import (filters, MessageHandler, ApplicationBuilder,
                          CommandHandler, ContextTypes, ConversationHandler,
                          CallbackQueryHandler)

import conv
import client
from course import Course

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))
GITHUB_URL = str(os.getenv("REPO_URL"))

(
    AWAIT_SELECTION,
    INPUT_COLLEGE,
    INPUT_DEPARTMENT,
    INPUT_COURSE_NUM,
    INPUT_SECTION,
    SUBMIT,
    CANCEL
) = map(chr, range(7))

(
    COLLEGE,
    DEPARTMENT,
    COURSE_NUM,
    SECTION,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED
) = map(chr, range(6))


def get_course_name(user_cache: dict[str, str]):
    """Format course name to match input for Course class"""
    return f"{user_cache[COLLEGE]} {user_cache[DEPARTMENT]}{user_cache[COURSE_NUM]} {user_cache[SECTION]}"


def update_cache(user_cache, user_course: dict[str, str] | None):
    """Updates user cache with course information and subscription status"""
    if user_course is None:
        user_cache[IS_SUBSCRIBED] = False
        return

    college, dep_num, section = user_course["name"].split()
    department, number = dep_num[:2], dep_num[2:]

    user_cache[COLLEGE] = college
    user_cache[DEPARTMENT] = department
    user_cache[COURSE_NUM] = number
    user_cache[SECTION] = section
    user_cache[IS_SUBSCRIBED] = True


def get_subscription_status(user_cache: dict, context: ContextTypes.DEFAULT_TYPE):
    """Check user subscription and updates cache"""
    is_subscribed = user_cache.get(IS_SUBSCRIBED)
    last_subscribed = user_cache.get(LAST_SUBSCRIBED)
    user_id = str(context._user_id)

    if is_subscribed is None:
        # update cache from db
        user_course = client.find_user_course(user_id)
        update_cache(user_cache, user_course)

    if last_subscribed is None:
        user = client.find_user(user_id)
        user_cache[LAST_SUBSCRIBED] = user["last_subscribed"] if user else None

    return user_cache[IS_SUBSCRIBED], user_cache[LAST_SUBSCRIBED]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (f"Welcome to BU Class Finder {Course.SEMESTER} {Course.YEAR}!\n"
            "Use the Menu button to get started.")
    await update.message.reply_text(text)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_cache = cast(dict, context.user_data)
    is_subscribed, last_subscribed = get_subscription_status(user_cache, context)
    last_subscribed = cast(datetime, last_subscribed)

    # Check user constraints (subscription status and time)
    if is_subscribed:
        course_name = get_course_name(user_cache)
        text = (f"*You are already subscribed to {course_name}*\!\n\n"
                "Use /unsubscribe to remove your subscription\."
                )
        await update.message.reply_markdown_v2(text)
        return ConversationHandler.END

    if last_subscribed:
        subscribed_elapsed = datetime.now() - last_subscribed
        remaining_time = Course.REFRESH_TIME - subscribed_elapsed.total_seconds()
        if remaining_time > 0:
            text = ("*You have recently subscribed to a course*\.\n\n"
                    f"Please wait {int(remaining_time // 60)} more minutes before subscribing\."
                    )
            await update.message.reply_markdown_v2(text)
            return ConversationHandler.END

    buttons = conv.get_main_buttons(user_cache)
    keyboard = InlineKeyboardMarkup(buttons)

    subscription_text = conv.get_subscription_text(user_cache)
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(subscription_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    else:
        await update.message.reply_markdown_v2(subscription_text, reply_markup=keyboard)

    return AWAIT_SELECTION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation"""
    # cast(dict, context.user_data).clear()
    query = update.callback_query
    # handle function entries: callback or command
    if query:
        await query.answer()
        await cast(Message, update.effective_message).edit_text("Transaction cancelled.")
    else:
        # await cast(Message, update.effective_message).delete()
        await context.bot.send_message(update.message.chat_id, "Transaction cancelled.")

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
    await query.message.delete()

    keyword = ""
    if query.data == INPUT_DEPARTMENT:
        keyword = "department"
    elif query.data == INPUT_COURSE_NUM:
        keyword = "course number"
    elif query.data == INPUT_SECTION:
        keyword = "section"

    await context.bot.send_message(query.message.chat_id, f"State the {keyword}", reply_markup=ForceReply())


async def save_college_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for chosen college"""
    query_data = update.callback_query.data
    user_cache = cast(dict, context.user_data)
    user_cache[COLLEGE] = query_data

    return await subscribe(update, context)


async def save_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check callback data and update cache for custom inputs"""
    await cast(Message, update.effective_message).delete()

    user_cache = cast(dict, context.user_data)
    reply = update.message.text.upper()
    if re.fullmatch("^[A-z]{2}$", reply):
        user_cache[DEPARTMENT] = reply
    elif re.fullmatch("^[1-9]{3}$", reply):
        user_cache[COURSE_NUM] = reply
    elif re.fullmatch("^[A-z]{1}[1-9]{1}$", reply):
        user_cache[SECTION] = reply
    else:
        await update.message.reply_text("Invalid input. Please try again.")

    return await subscribe(update, context)


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit to database"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Submitting...")

    user_cache = cast(dict, context.user_data)
    course_name = get_course_name(user_cache)
    user_id = str(context._user_id)
    client.update_db(course_name, user_id)
    curr_time = datetime.utcnow()
    client.update_user_subscription_time(user_id, curr_time)

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
    course_name = get_course_name(user_cache)
    client.remove_user(course_name, str(context._user_id))
    user_cache.clear()
    user_cache[IS_SUBSCRIBED] = False

    await cast(Message, update._effective_message).edit_text(f"You have been unsubscribed from {course_name}.")
    return ConversationHandler.END


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("• Use the bot commands to interact with the app\.\n"
            "• Each user is limited to *ONE* subscription at any time\.\n "
            "• Each user is allowed to change their subscription once every 24 hours\.\n"
            "• Once your class is available, you will be notified and your subscription will be cleared\.")
    await update.message.reply_markdown_v2(text)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("BU Class Finder is built with *python\-telegram\-bot*, "
            "*PyMongo*, *Selenium WebDriver*, and *Heroku*\. "
            f"It is open\-source\. View the source code [here]({GITHUB_URL})\.")
    await update.message.reply_markdown_v2(text)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("Sorry, I didn't understand that command. "
            "If you are currently in a subscription conversation, "
            "please end it first,\nor use /cancel if you are stuck.")
    await update.message.reply_text(text)


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
        entry_points=[CommandHandler("subscribe", subscribe)],  # type: ignore
        states={
            AWAIT_SELECTION: selection_handlers,  # type: ignore
        },
        fallbacks=[
            CallbackQueryHandler(save_college_input, pattern="^[A-Z]{3}$"),
            MessageHandler(filters.REPLY, save_custom_input),
            CallbackQueryHandler(cancel, pattern="^" + CANCEL + "$"),
            CommandHandler("cancel", cancel)
        ],  # type: ignore
    )
    unsubscribe_handler = ConversationHandler(
        entry_points=[CommandHandler(
            "unsubscribe", unsubscribe_dialog)],  # type: ignore
        states={
            AWAIT_SELECTION: [CallbackQueryHandler(unsubscribe, pattern="^" + SUBMIT + "$")], # type: ignore
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^" + CANCEL + "$"),
            CommandHandler("cancel", cancel)
        ],  # type: ignore
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
