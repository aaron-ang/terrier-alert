"""Module for representing and managing Boston University courses."""

from dataclasses import dataclass, field, InitVar

import pendulum
from curl_cffi import requests
from pydantic import BaseModel


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
    sem_code: int = field(init=False)
    formatted_params: str = field(init=False)
    bin_url: str = field(init=False)
    reg_url: str = field(init=False)
    reg_option_url: str = field(init=False)

    def __post_init__(self, course_name: str) -> None:
        # Parse course components
        college, dep_num, section = course_name.split()
        department, number = dep_num[:2], dep_num[2:]

        # Get semester info
        semester, year = self.get_sem_year().split()
        year_num = int(year) + (1 if semester == "Fall" else 0)
        sem_code = 3 if semester == "Fall" else 4

        # Build URL parameters
        params = (
            f"&term=2251"  # TODO: figure out term code. Spring 2025: 2251
            f"&subject={college}{department}"
            f"&catalog_nbr={number}"
        )

        # Set all attributes
        for name, value in {
            "college": college.upper(),
            "department": department.upper(),
            "number": number,
            "section": section.upper(),
            "year": year_num,
            "sem_code": sem_code,
            "formatted_params": params,
            "bin_url": BASE_BIN_URL + params,
            "reg_url": BASE_REG_URL + params,
            "reg_option_url": BASE_REG_OPTION_URL + params,
        }.items():
            object.__setattr__(self, name, value)

    @staticmethod
    def get_sem_year() -> str:
        """Returns the current academic semester and year.

        Format: "<Semester> <Year>" where Semester is Fall/Spring
        """
        now = pendulum.now()
        semester = "Fall" if 4 <= now.month <= 9 else "Spring"
        year = now.year + (1 if semester == "Spring" and now.month >= 10 else 0)
        return f"{semester} {year}"

    def _course_name(self) -> str:
        """Returns the standardized course name string."""
        return f"{self.college} {self.department}{self.number} {self.section}"

    def __repr__(self) -> str:
        return self._course_name()


class CourseResponse(BaseModel):
    class_section: str
    subject: str
    catalog_nbr: str
    wait_tot: int
    enrollment_available: int


def get_course_section(course: Course):
    response = requests.get(course.bin_url, impersonate="chrome")
    response.raise_for_status()
    data: list = response.json()

    try:
        course_section = next(x for x in data if x["class_section"] == course.section)
    except StopIteration:
        first_section = data[0]
        first_section = f"{first_section['subject']} {first_section['catalog_nbr']} {first_section['class_section']}"
        raise ValueError(f"{course} was not found. Did you mean {first_section}?")

    return CourseResponse(**course_section)
