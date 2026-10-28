"""Seat availability lookups for BU class sections.

`CourseSearch` is the seam between the finder and wherever seat data comes from.
`BUClassSearch` is the adapter for BU's public class search.
"""

from dataclasses import dataclass
from typing import Protocol

from curl_cffi import requests
from pydantic import BaseModel, ValidationError

from utils.constants import FALL_SEMESTER, SPRING_SEMESTER, SUMMER_SEMESTER
from utils.models import Course

BASE_SEARCH_URL = (
    "https://public.mybustudent.bu.edu/psc/BUPRD/EMPLOYEE/SA/s/"
    "WEBLIB_HCX_CM.H_CLASS_SEARCH.FieldFormula.IScript_ClassSearch"
)
TERM_CODES = {FALL_SEMESTER: 8, SPRING_SEMESTER: 1, SUMMER_SEMESTER: 5}
REQUEST_TIMEOUT_SECONDS = 20


class SearchUnavailable(Exception):
    """The seat data source is down; no section can be checked right now."""


class UnexpectedResponse(SearchUnavailable):
    """The data source answered in a shape the parser does not understand."""


class SectionNotFound(Exception):
    """The section does not exist in the given semester."""


@dataclass(frozen=True)
class Section:
    enrollment_available: int
    wait_tot: int


class CourseSearch(Protocol):
    async def lookup(self, course: Course, semester: str) -> Section:
        """Return seat counts for `course` in `semester` (e.g. "Fall 2026").

        Raises:
            SectionNotFound: The section is not offered that semester.
            SearchUnavailable: The data source cannot answer right now.
        """
        ...


class ClassResponse(BaseModel):
    class_section: str
    subject: str
    catalog_nbr: str
    wait_tot: int
    enrollment_available: int


def term_code(semester: str) -> str:
    """Convert "Fall 2026" to BU's term code "2268"."""
    name, year = semester.split()
    year_num = int(year)
    return f"{year_num // 1000}{year_num % 1000}{TERM_CODES[name]}"


def catalog_number(course: Course, semester: str) -> str:
    """BU suffixes summer catalog numbers with "S"."""
    if semester.startswith(SUMMER_SEMESTER) and not course.number.endswith("S"):
        return course.number + "S"
    return course.number


def find_section(course: Course, payload: object) -> Section:
    """Pick `course`'s section out of a class search response."""
    if not isinstance(payload, dict) or not isinstance(payload.get("classes"), list):
        raise UnexpectedResponse(f"Unexpected class search response for {course}")

    classes = [c for c in payload["classes"] if isinstance(c, dict)]
    match = next((c for c in classes if c.get("class_section") == course.section), None)
    if match is not None:
        try:
            found = ClassResponse(**match)
        except ValidationError as e:
            raise UnexpectedResponse(
                f"Unexpected class search response for {course}"
            ) from e
        return Section(found.enrollment_available, found.wait_tot)

    msg = f"{course} was not found."
    if classes:
        first = classes[0]
        suggestion = " ".join(
            str(first.get(k, "")) for k in ("subject", "catalog_nbr", "class_section")
        )
        msg += f" Did you mean {suggestion}?"
    raise SectionNotFound(msg)


class BUClassSearch:
    """Reads BU's public class search (no login required)."""

    async def lookup(self, course: Course, semester: str) -> Section:
        params = {
            "institution": "BU001",
            "term": term_code(semester),
            "subject": f"{course.college}{course.department}",
            "catalog_nbr": catalog_number(course, semester),
        }
        try:
            async with requests.AsyncSession(impersonate="chrome") as session:
                response = await session.get(
                    BASE_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
                )
        except requests.RequestsError as e:
            raise SearchUnavailable(f"BU class search unreachable: {e}") from e

        if response.status_code != 200:
            raise SearchUnavailable(
                f"BU class search returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as e:
            raise SearchUnavailable("BU class search returned non-JSON") from e

        return find_section(course, payload)
