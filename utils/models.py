"""Module for representing Boston University courses and terms."""

import re
from dataclasses import dataclass

import pendulum

from utils.constants import (
    FALL_SEMESTER,
    SPRING_SEMESTER,
    SUMMER_SEMESTER,
)

COURSE_PATTERN = re.compile(r"^([A-Z]{3}) ([A-Z]{2})(\d{3}S?) ([A-Z][A-Z0-9])$")


def get_sem_year(now: pendulum.DateTime | None = None) -> str:
    """Return the semester open for registration, e.g. "Spring 2027"."""
    now = now or pendulum.now()
    month, year = now.month, now.year

    if 4 <= month <= 9:
        semester = FALL_SEMESTER
    elif month > 9 or month <= 2:
        semester = SPRING_SEMESTER
    else:
        semester = SUMMER_SEMESTER

    if semester == SPRING_SEMESTER and month >= 10:
        year += 1

    return f"{semester} {year}"


@dataclass(frozen=True)
class Course:
    """A Boston University class section.

    Format: <college> <department><number> <section>
    Example: "CAS CS111 A1"
    """

    college: str
    department: str
    number: str
    section: str

    @classmethod
    def parse(cls, course_name: str) -> "Course":
        """Parse a course name, raising ValueError if it is malformed."""
        match = COURSE_PATTERN.fullmatch(" ".join(course_name.upper().split()))
        if not match:
            raise ValueError(f"Invalid course name: {course_name!r}")
        return cls(*match.groups())

    def __str__(self) -> str:
        return f"{self.college} {self.department}{self.number} {self.section}"
