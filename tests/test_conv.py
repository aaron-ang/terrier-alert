import os
import sys
import pytest
from telegram import InlineKeyboardButton

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import Message, InputStates
from utils.conv import (
    COLLEGES,
    get_main_buttons,
    get_college_buttons,
    get_confirmation_buttons,
    get_course,
    get_subscription_md,
    fields_equal,
)
from utils.models import Course


def test_get_main_buttons_empty_cache():
    buttons = get_main_buttons({})
    assert len(buttons) == 3  # 2 rows of inputs + cancel
    assert buttons[-1][0].text == "Cancel"
    assert buttons[-1][0].callback_data == InputStates.CANCEL


def test_get_main_buttons_with_data():
    cache = {
        Message.COLLEGE: "CAS",
        Message.DEPARTMENT: "CS",
        Message.COURSE_NUM: "111",
        Message.SECTION: "A1",
    }
    buttons = get_main_buttons(cache)
    assert len(buttons) == 4  # 2 rows of inputs + submit + cancel
    assert buttons[-2][0].text == "Submit"
    assert buttons[-2][0].callback_data == InputStates.SUBMIT
    assert buttons[0][0].text == "Edit College"
    assert buttons[0][1].text == "Edit Department"
    assert buttons[1][0].text == "Edit Course"
    assert buttons[1][1].text == "Edit Section"


def test_get_college_buttons():
    buttons = get_college_buttons()
    assert len(buttons) == 4  # 10 colleges split into groups of 3
    assert all(
        isinstance(button, InlineKeyboardButton) for row in buttons for button in row
    )
    assert all(
        college in [button.text for row in buttons for button in row]
        for college in COLLEGES
    )


def test_get_confirmation_buttons():
    buttons = get_confirmation_buttons()
    assert len(buttons) == 1
    assert len(buttons[0]) == 2  # Yes and No buttons
    assert buttons[0][0].text == "Yes"
    assert buttons[0][1].text == "No"


def test_get_course():
    cache = {
        Message.COLLEGE: "CAS",
        Message.DEPARTMENT: "CS",
        Message.COURSE_NUM: "111",
        Message.SECTION: "A1",
    }
    course = get_course(cache)
    assert course == Course("CAS CS111 A1")


def test_get_course_name_missing_fields():
    with pytest.raises(AssertionError):
        get_course({Message.COLLEGE: "CAS"})


def test_get_subscription_md():
    cache = {
        Message.COLLEGE: "CAS",
        Message.DEPARTMENT: "CS",
        Message.COURSE_NUM: "111",
        Message.SECTION: "A1",
    }
    md = get_subscription_md(cache)
    assert "*College:*" in md
    assert "CAS" in md
    assert "*Department:*" in md
    assert "CS" in md
    assert "*Course:*" in md
    assert "111" in md
    assert "*Section:*" in md
    assert "A1" in md


def test_fields_equal():
    cache1 = {Message.COLLEGE: "CAS", Message.DEPARTMENT: "CS"}
    cache2 = {Message.COLLEGE: "CAS", Message.DEPARTMENT: "CS"}
    cache3 = {Message.COLLEGE: "CAS", Message.DEPARTMENT: "MA"}

    assert fields_equal(cache1, cache2, {Message.COLLEGE, Message.DEPARTMENT})
    assert not fields_equal(cache1, cache3, {Message.COLLEGE, Message.DEPARTMENT})
