# Standard library imports
import os
import sys

# Third-party imports
from dotenv import load_dotenv
from telegram import CallbackQuery
from telegram.ext import ContextTypes

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import Database
from utils.constants import Environment, TimeConstants, SEM_YEAR, USER_LIST, COURSE_NAME
from utils.models import Course

# Constants
load_dotenv()
FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
REG_SCREENS = {
    "title": "Add Classes - Display",
    "options": "Registration Options",
    "confirmation": "Add Classes - Confirmation",
}

# Global variables
DB: Database | None = None
BOT = None


async def register_course(env: Environment, user_cache: dict, query: CallbackQuery):
    """Regiser a course for the user, to be called by `bot.py`"""
    pass


async def search_courses() -> None:
    """Process all course subscriptions."""
    for course_doc in DB.get_all_courses():
        course = Course(course_doc[COURSE_NAME])
        users = list(course_doc[USER_LIST])

        if not users:
            DB.remove_course(str(course))
            continue

        if course_doc[SEM_YEAR] != Course.get_sem_year():
            await handle_expired_semester(course, course_doc[SEM_YEAR], users)
            continue

        await process_course(course, users)


async def handle_expired_semester(
    course: Course, semester: str, users: list[str]
) -> None:
    """Handle courses from expired semesters."""
    msg = (
        f"You have been unsubscribed from {course} "
        f"since the deadline to add courses for {semester} has passed."
    )
    await notify_users_and_unsubscribe(course, msg, users)


async def process_course(course: Course, users: list[str]):
    """Checks for edge cases and course availability. Handles notifications for each case."""
    try:
        course_response = course.get_course_section()
    except ValueError as exc:
        await notify_users_and_unsubscribe(course, str(exc), users)
        return

    if course_response.enrollment_available > 0:
        waitlist_cnt = course_response.wait_tot
        msg = (
            f"{course} is now available! (with {waitlist_cnt} students on the waitlist)"
        )
        await notify_users_and_unsubscribe(course, msg, users)


async def notify_users_and_unsubscribe(course: Course, msg: str, users: list[str]):
    """Notifies each user on Telegram and unsubscribes them from the course."""
    for uid in users:
        await BOT.send_message(
            chat_id=uid,
            text=msg,
            write_timeout=TimeConstants.TIMEOUT_SECONDS,
        )
        DB.unsubscribe(course, uid)


def init(context: ContextTypes.DEFAULT_TYPE):
    global BOT, DB
    BOT = context.bot
    DB = context.job.data["db"]


async def run(context: ContextTypes.DEFAULT_TYPE):
    init(context)
    await search_courses()
