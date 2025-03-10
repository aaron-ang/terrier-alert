"""Module for representing and managing Boston University courses."""

from dataclasses import dataclass, field, InitVar

import pendulum
from curl_cffi import requests
from pydantic import BaseModel

from utils.constants import (
    FALL_SEMESTER,
    SPRING_SEMESTER,
    SUMMER_SEMESTER,
)


# Base URLs for student portal
BASE_BIN_URL = (
    "https://public.mybustudent.bu.edu/psc/BUPRD/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_CLASS_SEARCH.FieldFormula.IScript_ClassSearch?"
    "institution=BU001"
)
BASE_REG_URL = (
    "https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1"
    "?ModuleName=reg%2Fadd%2Fbrowse_schedule.pl&SearchOptionDesc=Class+Number&SearchOptionCd=S"
)
BASE_REG_OPTION_URL = (
    "https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1"
    "?ModuleName=reg/option/_start.pl"
)


@dataclass(frozen=True)
class Course:
    """Represents a Boston University course with registration capabilities.

    Format: <college> <department><number> <section>
    Example: "CAS CS111 A1"
    """

    course_name: InitVar[str]
    college: str = field(init=False)
    department: str = field(init=False)
    number: str = field(init=False)
    section: str = field(init=False)
    year: int = field(init=False)
    term_code: str = field(init=False)
    bin_url: str = field(init=False)
    reg_url: str = field(init=False)
    reg_option_url: str = field(init=False)

    def __post_init__(self, course_name: str) -> None:
        # Parse course components
        college, dep_num, section = course_name.split()
        department, number = dep_num[:2], dep_num[2:]

        # Get semester info
        semester, year = self.get_sem_year().split()
        year_num = int(year)
        sem_code = {FALL_SEMESTER: 8, SPRING_SEMESTER: 1, SUMMER_SEMESTER: 5}[semester]
        term_code = f"{year_num // 1000}{year_num % 1000}{sem_code}"

        # Build URL parameter string
        params = f"&term={term_code}&subject={college}{department}&catalog_nbr={number}"

        # Set all attributes
        attrs = {
            "college": college.upper(),
            "department": department.upper(),
            "number": number,
            "section": section.upper(),
            "year": year_num,
            "term_code": term_code,
            "bin_url": BASE_BIN_URL + params,
            "reg_url": BASE_REG_URL + params,
            "reg_option_url": BASE_REG_OPTION_URL + params,
        }

        for name, value in attrs.items():
            object.__setattr__(self, name, value)

    @staticmethod
    def get_sem_year() -> str:
        """Returns the current academic semester and year as a tuple."""
        now = pendulum.now()
        month = now.month
        year = now.year

        if 4 <= month <= 9:
            semester = FALL_SEMESTER
        elif month > 9 or month <= 2:
            semester = SPRING_SEMESTER
        else:
            semester = SUMMER_SEMESTER

        if semester == SPRING_SEMESTER and month >= 10:
            year += 1

        return f"{semester} {year}"

    def __repr__(self) -> str:
        return f"{self.college} {self.department}{self.number} {self.section}"


class CourseResponse(BaseModel):
    """Model representing course information from the API response."""

    class_section: str
    subject: str
    catalog_nbr: str
    wait_tot: int
    enrollment_available: int


def get_course_section(course: Course) -> CourseResponse:
    """Fetches course section information from BU's API.

    Args:
        course: The Course object to query

    Returns:
        CourseResponse with section information

    Raises:
        ValueError: If the specified section is not found
    """
    response = requests.get(course.bin_url, impersonate="chrome")
    response.raise_for_status()
    classes: list = response.json()["classes"]

    try:
        course_section = next(
            x for x in classes if x["class_section"] == course.section
        )
    except StopIteration:
        error_msg = f"{course} was not found."
        if classes and (first_section := classes[0]):
            section_name = f"{first_section['subject']} {first_section['catalog_nbr']} {first_section['class_section']}"
            error_msg += f" Did you mean {section_name}?"
        raise ValueError(error_msg)

    return CourseResponse(**course_section)
