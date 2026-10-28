from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from curl_cffi import requests

from src.search import (
    BUClassSearch,
    SearchUnavailable,
    Section,
    SectionNotFound,
    UnexpectedResponse,
    catalog_number,
    find_section,
    term_code,
)
from utils.models import Course, get_sem_year


def bu_class(section: str, available: int = 0, waitlist: int = 0) -> dict:
    return {
        "class_section": section,
        "subject": "CASCS",
        "catalog_nbr": "111",
        "wait_tot": waitlist,
        "enrollment_available": available,
    }


def test_term_code():
    assert term_code("Fall 2026") == "2268"
    assert term_code("Spring 2027") == "2271"
    assert term_code("Summer 2027") == "2275"


def test_catalog_number_adds_summer_suffix():
    course = Course.parse("CAS CS111 A1")
    assert catalog_number(course, "Fall 2026") == "111"
    assert catalog_number(course, "Summer 2027") == "111S"
    assert catalog_number(Course.parse("CAS CS111S A1"), "Summer 2027") == "111S"


def test_find_section():
    course = Course.parse("CAS CS111 B1")
    payload = {"classes": [bu_class("A1"), bu_class("B1", available=4, waitlist=2)]}
    assert find_section(course, payload) == Section(enrollment_available=4, wait_tot=2)


def test_find_section_missing_suggests_alternative():
    with pytest.raises(SectionNotFound, match="Did you mean CASCS 111 A1"):
        find_section(Course.parse("CAS CS111 Z1"), {"classes": [bu_class("A1")]})


def test_find_section_no_classes():
    with pytest.raises(SectionNotFound, match="^CAS CS999 A1 was not found.$"):
        find_section(Course.parse("CAS CS999 A1"), {"classes": []})


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"classes": "x"}, {"classes": [{"class_section": "A1"}]}]
)
def test_find_section_unexpected_shape(payload):
    with pytest.raises(UnexpectedResponse):
        find_section(Course.parse("CAS CS111 A1"), payload)


def test_find_section_ignores_malformed_other_rows():
    payload = {"classes": [{"class_section": "A2"}, "junk", bu_class("A1", 5)]}
    assert find_section(Course.parse("CAS CS111 A1"), payload) == Section(5, 0)


def mock_session(response=None, error=None):
    session = MagicMock()
    session.get = AsyncMock(return_value=response, side_effect=error)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return patch("src.search.requests.AsyncSession", return_value=session)


def response(status: int, json=None):
    r = MagicMock(status_code=status)
    if isinstance(json, Exception):
        r.json.side_effect = json
    else:
        r.json.return_value = json
    return r


@pytest.mark.asyncio
async def test_lookup_sends_bu_params():
    with mock_session(response(200, {"classes": [bu_class("A1", 1)]})) as session_cls:
        section = await BUClassSearch().lookup(
            Course.parse("CAS CS111 A1"), "Fall 2026"
        )

    assert section == Section(1, 0)
    params = session_cls.return_value.get.call_args.kwargs["params"]
    assert params == {
        "institution": "BU001",
        "term": "2268",
        "subject": "CASCS",
        "catalog_nbr": "111",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"response": response(503)},
        {"response": response(200, ValueError("not json"))},
        {"error": requests.RequestsError("timed out")},
    ],
    ids=["http-503", "non-json", "network-error"],
)
async def test_lookup_outages_raise_search_unavailable(kwargs):
    with mock_session(**kwargs), pytest.raises(SearchUnavailable):
        await BUClassSearch().lookup(Course.parse("CAS CS111 A1"), "Fall 2026")


async def live_lookup(course_name: str) -> Section:
    try:
        return await BUClassSearch().lookup(Course.parse(course_name), get_sem_year())
    except UnexpectedResponse:
        raise
    except SearchUnavailable as e:
        pytest.skip(f"BU class search unavailable: {e}")
    except SectionNotFound as e:
        # Sections come and go each term; only the response shape is under test
        pytest.skip(f"Section not offered this term: {e}")


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_lookup():
    section = await live_lookup("CAS EC101 A1")
    assert section.enrollment_available >= 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_missing_section():
    try:
        await BUClassSearch().lookup(Course.parse("CAS CS111 Z1"), get_sem_year())
    except UnexpectedResponse:
        raise
    except SearchUnavailable as e:
        pytest.skip(f"BU class search unavailable: {e}")
    except SectionNotFound:
        return
    pytest.fail("CAS CS111 Z1 should not exist")
