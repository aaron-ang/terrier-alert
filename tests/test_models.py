import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.models import Course, get_course_section


def test_course_init():
    course_name = "CAS CS111 A1"
    course = Course(course_name)
    assert course.college == "CAS"
    assert course.department == "CS"
    assert "111" in course.number
    assert course.section == "A1"


def test_course_response():
    course = Course("CAS EC101 A1")
    course_response = get_course_section(course)
    assert course_response.subject == f"{course.college}{course.department}"
    assert course_response.catalog_nbr == course.number
    assert course_response.class_section == course.section


def test_missing_course():
    with pytest.raises(Exception):
        course = Course("CAS CS999 A1")
        get_course_section(course)

    with pytest.raises(Exception) as e_info:
        course = Course("CAS CS111 Z1")
        get_course_section(course)

    assert e_info.type is ValueError
    assert f"{course} was not found. Did you mean CASCS 111" in e_info.value.args[0]
