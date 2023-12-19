"""This module contains all the text and buttons used in the bot."""

import os
from dotenv import load_dotenv
from telegram import InlineKeyboardButton

from utils.constants import (
    INPUT_COLLEGE,
    INPUT_DEPARTMENT,
    INPUT_COURSE_NUM,
    INPUT_SECTION,
    SUBMIT,
    CANCEL,
    COLLEGE,
    DEPARTMENT,
    COURSE_NUM,
    SECTION,
    FORM_FIELDS,
)
from utils.course import Course


load_dotenv()

GITHUB_URL = os.getenv("GITHUB_URL")
WELCOME_TEXT = (
    f"Welcome to Terrier Alert {Course.get_sem_year()}!\n"
    "Use the Menu button to get started."
)
NOT_SUBSCRIBED_TEXT = (
    "You are not subscribed to any course. Use /subscribe to start a subscription."
)
UNSUBSCRIBE_TEXT = (
    "You can only resubscribe 24 hours after your last subscription. "
    "Are you sure you want to unsubscribe?"
)
HELP_TEXT = (
    "• Use the bot commands to interact with the app\.\n"
    "• Each user is limited to *ONE* subscription at any time\.\n"
    "• Each user is allowed to change their subscription once every 24 hours\.\n"
    "• Once your class is available, you will be notified and your subscription will be cleared\."
)
ABOUT_TEXT = (
    "Terrier Alert is built with "
    "*python\-telegram\-bot*, *PyMongo*, *Selenium WebDriver*, and *Heroku*\. "
    f"Check out the code [here]({GITHUB_URL})\."
)
UNKNOWN_CMD_TEXT = (
    "Sorry, I didn't understand that command. If you are currently in a subscription conversation, "
    "please end it first,\nor use /cancel if you are stuck."
)
FEEDBACK_TEXT = "Enter and submit your feedback here. Use /cancel to abort."
FEEDBACK_SUCCESS_TEXT = "Feedback received. Thank you!"
FEEDBACK_FAILURE_TEXT = "Feedback failed to send. Please try again later."
COLLEGES = ["CAS", "CDS", "COM", "ENG", "SAR", "QST", "CGS", "SPH", "SED", "PDP"]


def get_main_buttons(user_cache: dict):
    """Return subscription form buttons"""
    buttons = [
        [
            InlineKeyboardButton(text="Input College", callback_data=INPUT_COLLEGE),
            InlineKeyboardButton(
                text="Input Department", callback_data=INPUT_DEPARTMENT
            ),
        ],
        [
            InlineKeyboardButton(text="Input Course", callback_data=INPUT_COURSE_NUM),
            InlineKeyboardButton(text="Input Section", callback_data=INPUT_SECTION),
        ],
        [InlineKeyboardButton(text="Cancel", callback_data=CANCEL)],
    ]

    if not user_cache:
        return buttons

    for changed_fields in user_cache:
        if changed_fields == COLLEGE:
            buttons[0][0] = InlineKeyboardButton(
                text="Edit College", callback_data=INPUT_COLLEGE
            )
        elif changed_fields == DEPARTMENT:
            buttons[0][1] = InlineKeyboardButton(
                text="Edit Department", callback_data=INPUT_DEPARTMENT
            )
        elif changed_fields == COURSE_NUM:
            buttons[1][0] = InlineKeyboardButton(
                text="Edit Course", callback_data=INPUT_COURSE_NUM
            )
        elif changed_fields == SECTION:
            buttons[1][1] = InlineKeyboardButton(
                text="Edit Section", callback_data=INPUT_SECTION
            )

    if FORM_FIELDS.issubset(user_cache):
        buttons.insert(-1, [InlineKeyboardButton(text="Submit", callback_data=SUBMIT)])

    return buttons


def get_college_buttons():
    """Return college selection buttons"""
    cols = 3
    rows = []
    for i in range(0, len(COLLEGES), cols):
        rows.append(
            [
                InlineKeyboardButton(text=college, callback_data=college)
                for college in COLLEGES[i : i + cols]
            ]
        )
    return rows


def get_confirmation_buttons():
    """Return confirmation buttons"""
    return [
        [
            InlineKeyboardButton("Yes", callback_data=SUBMIT),
            InlineKeyboardButton("No", callback_data=CANCEL),
        ]
    ]


def get_course_name(user_cache: dict[str, str]):
    """Format course name to match input for Course class"""
    return f"{user_cache[COLLEGE]} {user_cache[DEPARTMENT]}{user_cache[COURSE_NUM]} {user_cache[SECTION]}"


def get_subscription_text(user_cache: dict):
    """Format current subscription form data"""
    college = "" if not user_cache.get(COLLEGE) else user_cache[COLLEGE] + "\n"
    department = "" if not user_cache.get(DEPARTMENT) else user_cache[DEPARTMENT] + "\n"
    course_num = "" if not user_cache.get(COURSE_NUM) else user_cache[COURSE_NUM] + "\n"
    section = "" if not user_cache.get(SECTION) else user_cache[SECTION]

    return (
        f"*College:*\n{college}\n"
        f"*Department:*\n{department}\n"
        f"*Course:*\n{course_num}\n"
        f"*Section:*\n{section}"
    )


def form_fields_equal(cache1: dict, cache2: dict):
    """Check if two user caches have the same form fields"""
    for field in FORM_FIELDS:
        if cache1.get(field, None) != cache2.get(field, None):
            return False
    return True
