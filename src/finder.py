"""Periodic job that checks subscribed sections and notifies users."""

import logging

from telegram import Bot
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from src.db import Database
from src.search import CourseSearch, SearchUnavailable, SectionNotFound
from utils.constants import COURSE_NAME, SEM_YEAR, USER_LIST, TimeConstants
from utils.models import Course, get_sem_year

logger = logging.getLogger(__name__)


class Finder:
    """Checks every subscribed section once per `run`.

    When the search reports an outage, the run stops early and the admin
    channel is told once; it is told again when the search recovers.
    """

    def __init__(
        self, db: Database, search: CourseSearch, bot: Bot, admin_chat_id: str
    ):
        self.db = db
        self.search = search
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.search_down = False

    async def run(self, _context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
        semester = get_sem_year()
        for course_doc in list(self.db.get_all_courses()):
            try:
                course = Course.parse(course_doc[COURSE_NAME])
            except ValueError:
                logger.exception("Skipping malformed course document %s", course_doc)
                continue
            users = list(course_doc[USER_LIST])
            course_semester = course_doc[SEM_YEAR]

            if not users:
                self.db.remove_course(course, course_semester)
            elif course_semester != semester:
                msg = (
                    f"You have been unsubscribed from {course} "
                    f"since the deadline to add courses for {course_semester} has passed."
                )
                await self.notify_and_unsubscribe(course, msg, users)
            elif not await self.check(course, semester, users):
                return

    async def check(self, course: Course, semester: str, users: list[str]) -> bool:
        """Check one section. Return False if the search is down."""
        try:
            section = await self.search.lookup(course, semester)
        except SearchUnavailable as e:
            await self.set_search_down(True, str(e))
            return False
        except SectionNotFound as e:
            await self.set_search_down(False, "")
            await self.notify_and_unsubscribe(course, str(e), users)
            return True

        await self.set_search_down(False, "")
        if section.enrollment_available > 0:
            msg = (
                f"{course} is now available! "
                f"(with {section.wait_tot} students on the waitlist)"
            )
            await self.notify_and_unsubscribe(course, msg, users)
        return True

    async def notify_and_unsubscribe(self, course: Course, msg: str, users: list[str]):
        """Notify each user on Telegram and unsubscribe them from the course.

        Users who blocked the bot or deleted their chat are still unsubscribed.
        """
        for uid in users:
            try:
                await self.bot.send_message(
                    chat_id=uid, text=msg, write_timeout=TimeConstants.TIMEOUT_SECONDS
                )
            except (Forbidden, BadRequest) as e:
                logger.warning("Could not notify %s: %s", uid, e)
            self.db.unsubscribe(course, uid)

    async def set_search_down(self, down: bool, reason: str) -> None:
        if down == self.search_down:
            return
        self.search_down = down
        text = (
            f"Course search is down, alerts paused: {reason}"
            if down
            else "Course search is back up, alerts resumed."
        )
        logger.warning(text)
        try:
            await self.bot.send_message(chat_id=self.admin_chat_id, text=text)
        except TelegramError:
            logger.exception("Could not alert admin channel")
