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
BASE_SEARCH_URL = (
    "https://public.mybustudent.bu.edu/psc/BUPRD/EMPLOYEE/SA/s/WEBLIB_HCX_CM.H_CLASS_SEARCH.FieldFormula.IScript_ClassSearch?"
    "institution=BU001"
)


class CourseResponse(BaseModel):
    """Model representing course information from the API response."""

    class_section: str
    subject: str
    catalog_nbr: str
    wait_tot: int
    enrollment_available: int


@dataclass(frozen=True)
class Course:
    """Represents a Boston University course with registration capabilities.

    Format: <college> <department><number> <section>
    Example: "CAS CS111 A1"
    """

    course_name: InitVar[str]
    purge: InitVar[bool] = False
    college: str = field(init=False)
    department: str = field(init=False)
    number: str = field(init=False)
    section: str = field(init=False)
    search_url: str = field(init=False)

    def __post_init__(self, course_name: str, purge: bool):
        # Parse course components
        college, dep_num, section = course_name.split()
        department, number = dep_num[:2], dep_num[2:]

        attrs = {
            "college": college.upper(),
            "department": department.upper(),
            "number": number,
            "section": section.upper(),
        }

        for name, value in attrs.items():
            object.__setattr__(self, name, value)

        if purge:
            return

        # Build URL parameter string and adjust course number for summer semester
        term_code, catalog_nbr = self.get_term_and_catalog(number)
        params = f"&term={term_code}&subject={self.college}{self.department}&catalog_nbr={catalog_nbr}"

        attrs = {
            "number": catalog_nbr,
            "search_url": BASE_SEARCH_URL + params,
        }

        for name, value in attrs.items():
            object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        return f"{self.college} {self.department}{self.number} {self.section}"

    def get_term_and_catalog(self, number: str) -> tuple[str, str]:
        semester, year = self.get_sem_year().split()
        year_num = int(year)
        sem_code = {FALL_SEMESTER: 8, SPRING_SEMESTER: 1, SUMMER_SEMESTER: 5}[semester]

        if semester == SUMMER_SEMESTER and number[-1] != "S":
            number += "S"

        return f"{year_num // 1000}{year_num % 1000}{sem_code}", number

    @staticmethod
    def get_sem_year():
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

    def get_course_section(self) -> CourseResponse:
        """Fetches course section information from BU's API.

        Raises:
            ValueError: If the specified section is not found
        """
        response = requests.get(self.search_url, impersonate="chrome")
        response.raise_for_status()

        try:
            json_data = response.json()
            classes: list = json_data.get("classes", [])
            course_section = next(
                x for x in classes if x["class_section"] == self.section
            )
        except StopIteration:
            error_msg = f"{self} was not found."
            if classes and (first_section := classes[0]):
                section_name = f"{first_section['subject']} {first_section['catalog_nbr']} {first_section['class_section']}"
                error_msg += f" Did you mean {section_name}?"
            raise ValueError(error_msg)
        except Exception as e:
            raise LookupError(
                f"Error fetching course with URL {self.search_url}"
            ) from e

        return CourseResponse(**course_section)
