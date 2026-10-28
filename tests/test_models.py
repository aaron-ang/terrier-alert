import pendulum
import pytest

from utils.models import Course, get_sem_year


def test_course_parse():
    course = Course.parse("CAS CS111 A1")
    assert course == Course("CAS", "CS", "111", "A1")
    assert str(course) == "CAS CS111 A1"


def test_course_parse_normalizes_case_and_spaces():
    assert str(Course.parse("  cas   cs111 a1 ")) == "CAS CS111 A1"


def test_course_parse_keeps_summer_suffix():
    assert Course.parse("CAS CS111S A1").number == "111S"


@pytest.mark.parametrize(
    "name", ["", "CAS CS111", "CAS CS11 A1", "CA CS111 A1", "CAS CS111 A1 X"]
)
def test_course_parse_rejects_malformed(name):
    with pytest.raises(ValueError):
        Course.parse(name)


@pytest.mark.parametrize(
    "date, expected",
    [
        ("2026-01-15", "Spring 2026"),
        ("2026-02-28", "Spring 2026"),
        ("2026-03-01", "Summer 2026"),
        ("2026-04-01", "Fall 2026"),
        ("2026-09-30", "Fall 2026"),
        ("2026-10-01", "Spring 2027"),
        ("2026-12-31", "Spring 2027"),
    ],
)
def test_get_sem_year(date, expected):
    assert get_sem_year(pendulum.parse(date)) == expected
