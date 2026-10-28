from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Forbidden

from src.db import Database
from src.finder import Finder
from src.search import SearchUnavailable, Section, SectionNotFound
from utils.constants import COURSE_NAME, SEM_YEAR, USER_LIST
from utils.models import Course, get_sem_year

ADMIN_CHAT = "admin"


class FakeSearch:
    """Answers lookups from a dict of course name -> Section or exception."""

    def __init__(self, results: dict):
        self.results = results
        self.calls: list[str] = []

    async def lookup(self, course: Course, semester: str) -> Section:
        self.calls.append(str(course))
        result = self.results[str(course)]
        if isinstance(result, Exception):
            raise result
        return result


def course_doc(name: str, users: list[str], semester: str | None = None) -> dict:
    return {COURSE_NAME: name, USER_LIST: users, SEM_YEAR: semester or get_sem_year()}


def make_finder(docs: list[dict], results: dict):
    db = MagicMock(spec=Database)
    db.get_all_courses.return_value = docs
    bot = MagicMock()
    bot.send_message = AsyncMock()
    search = FakeSearch(results)
    return Finder(db, search, bot, ADMIN_CHAT), db, bot, search


def sent_to(bot, chat_id) -> list[str]:
    return [
        c.kwargs["text"]
        for c in bot.send_message.call_args_list
        if c.kwargs["chat_id"] == chat_id
    ]


@pytest.mark.asyncio
async def test_open_section_notifies_and_unsubscribes():
    finder, db, bot, _ = make_finder(
        [course_doc("CAS CS111 A1", ["u1", "u2"])],
        {"CAS CS111 A1": Section(enrollment_available=2, wait_tot=3)},
    )
    await finder.run()

    assert sent_to(bot, "u1") == [
        "CAS CS111 A1 is now available! (with 3 students on the waitlist)"
    ]
    assert len(sent_to(bot, "u2")) == 1
    assert db.unsubscribe.call_count == 2


@pytest.mark.asyncio
async def test_full_section_does_nothing():
    finder, db, bot, _ = make_finder(
        [course_doc("CAS CS111 A1", ["u1"])],
        {"CAS CS111 A1": Section(enrollment_available=0, wait_tot=10)},
    )
    await finder.run()

    bot.send_message.assert_not_called()
    db.unsubscribe.assert_not_called()


@pytest.mark.asyncio
async def test_missing_section_unsubscribes_with_reason():
    finder, db, bot, _ = make_finder(
        [course_doc("CAS CS111 Z1", ["u1"])],
        {"CAS CS111 Z1": SectionNotFound("CAS CS111 Z1 was not found.")},
    )
    await finder.run()

    assert sent_to(bot, "u1") == ["CAS CS111 Z1 was not found."]
    db.unsubscribe.assert_called_once()


@pytest.mark.asyncio
async def test_outage_stops_run_and_alerts_admin_once():
    finder, db, bot, search = make_finder(
        [course_doc("CAS CS111 A1", ["u1"]), course_doc("CAS CS112 A1", ["u2"])],
        {
            "CAS CS111 A1": SearchUnavailable("HTTP 503"),
            "CAS CS112 A1": Section(1, 0),
        },
    )
    await finder.run()
    await finder.run()

    assert search.calls == ["CAS CS111 A1", "CAS CS111 A1"]
    assert sent_to(bot, ADMIN_CHAT) == [
        "Course search is down, alerts paused: HTTP 503"
    ]
    db.unsubscribe.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_alerts_admin():
    finder, _, bot, search = make_finder(
        [course_doc("CAS CS111 A1", ["u1"])],
        {"CAS CS111 A1": SearchUnavailable("HTTP 503")},
    )
    await finder.run()
    search.results["CAS CS111 A1"] = Section(0, 0)
    await finder.run()
    await finder.run()

    assert sent_to(bot, ADMIN_CHAT) == [
        "Course search is down, alerts paused: HTTP 503",
        "Course search is back up, alerts resumed.",
    ]


@pytest.mark.asyncio
async def test_blocked_user_is_still_unsubscribed_and_others_notified():
    finder, db, bot, _ = make_finder(
        [course_doc("CAS CS111 A1", ["blocked", "u2"])],
        {"CAS CS111 A1": Section(1, 0)},
    )

    async def send_message(chat_id, **kwargs):
        if chat_id == "blocked":
            raise Forbidden("bot was blocked by the user")

    bot.send_message.side_effect = send_message
    await finder.run()

    assert [c.args[1] for c in db.unsubscribe.call_args_list] == ["blocked", "u2"]


@pytest.mark.asyncio
async def test_expired_semester_unsubscribes_without_lookup():
    finder, db, bot, search = make_finder(
        [course_doc("CAS CS111 A1", ["u1"], semester="Fall 2000")], {}
    )
    await finder.run()

    assert search.calls == []
    assert "deadline to add courses for Fall 2000" in sent_to(bot, "u1")[0]
    db.unsubscribe.assert_called_once_with(Course.parse("CAS CS111 A1"), "u1")


@pytest.mark.asyncio
async def test_empty_course_is_removed_for_its_semester():
    finder, db, _, search = make_finder(
        [course_doc("CAS CS111 A1", [], semester="Fall 2000")], {}
    )
    await finder.run()

    assert search.calls == []
    db.remove_course.assert_called_once_with(Course.parse("CAS CS111 A1"), "Fall 2000")


@pytest.mark.asyncio
async def test_malformed_course_is_skipped():
    finder, db, _, search = make_finder(
        [course_doc("garbage", ["u1"]), course_doc("CAS CS111 A1", ["u2"])],
        {"CAS CS111 A1": Section(0, 0)},
    )
    await finder.run()

    assert search.calls == ["CAS CS111 A1"]
