"""This module contains the Course class, which is used to represent a course at BU."""

from typing import ClassVar
from dataclasses import dataclass, field, InitVar

import pendulum


@dataclass(frozen=True)
class Course:
    _bin_prefix: ClassVar[str] = (
        "https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1?ModuleName="
        "univschr.pl&SearchOptionDesc=Class+Number&SearchOptionCd=S"
    )
    _reg_prefix: ClassVar[str] = (
        "https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1?ModuleName="
        "reg%2Fadd%2Fbrowse_schedule.pl&SearchOptionDesc=Class+Number&SearchOptionCd=S"
    )
    _reg_option_prefix: ClassVar[str] = (
        "https://www.bu.edu/link/bin/uiscgi_studentlink.pl/1?ModuleName="
        "reg/option/_start.pl"
    )
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

    def __post_init__(self, course_name: str):
        college, dep_num, section = course_name.split()
        department, number = dep_num[:2], dep_num[2:]
        semester, year = self.get_sem_year().split()
        year = int(year)

        object.__setattr__(self, "college", college.upper())
        object.__setattr__(self, "department", department.upper())
        object.__setattr__(self, "number", number)
        object.__setattr__(self, "section", section.upper())
        object.__setattr__(self, "year", year + 1 if semester == "Fall" else year)
        object.__setattr__(self, "sem_code", 3 if semester == "Fall" else 4)
        object.__setattr__(
            self,
            "formatted_params",
            f"&ViewSem={semester}+{year}&KeySem={self.year}{self.sem_code}&College={self.college}"
            f"&Dept={self.department}&Course={self.number}&Section={self.section}",
        )
        object.__setattr__(self, "bin_url", self._bin_prefix + self.formatted_params)
        object.__setattr__(self, "reg_url", self._reg_prefix + self.formatted_params)
        object.__setattr__(
            self, "reg_option_url", self._reg_option_prefix + self.formatted_params
        )

    @staticmethod
    def get_sem_year():
        now = pendulum.now()
        semester = "Fall" if 3 <= now.month <= 9 else "Spring"
        year = (
            now.year + 1
            if (semester == "Spring" and 10 <= now.month <= 12)
            else now.year
        )
        return f"{semester} {year}"

    def get_course_name(self):
        return f"{self.college} {self.department}{self.number} {self.section}"
