"""This module contains all the text and buttons used in the bot."""

import os
from dotenv import load_dotenv
from telegram import InlineKeyboardButton

from utils.constants import *
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
NOT_AVAILABLE_TEXT = (
    "The course you are subscribed to is not available yet. "
    "You will be notified when it becomes available."
)
ALREADY_SUBSCRIBED_MD = (
    "*You are already subscribed to @*\!\n\n"
    f"Use /unsubscribe to end your subscription\."
)
RECENTLY_SUBSCRIBED_MD = (
    "*You have recently subscribed to a course*\.\n\n"
    f"Please wait until @ to subscribe\."
)
UNSUBSCRIBE_TEXT = (
    "You can only resubscribe 24 hours after your last subscription. "
    "Are you sure you want to unsubscribe?"
)
HELP_MD = (
    "• Use the bot commands to interact with the app\.\n"
    "• Each user is limited to *ONE* subscription at any time\.\n"
    "• Each user is allowed to change their subscription once every 24 hours\.\n"
    "• Once your class is available, you will be notified and your subscription will be cleared\."
)
ABOUT_MD = (
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

    if all(field in user_cache for field in FORM_FIELDS):
        buttons.insert(-1, [InlineKeyboardButton(text="Submit", callback_data=SUBMIT)])

    return buttons


def get_cred_buttons(user_cache: dict):
    """Return user credential buttons"""
    buttons = [
        [
            InlineKeyboardButton(text="Input Username", callback_data=INPUT_USERNAME),
            InlineKeyboardButton(text="Input Password", callback_data=INPUT_PASSWORD),
        ],
        [InlineKeyboardButton(text="Cancel", callback_data=CANCEL)],
    ]

    for changed_fields in user_cache:
        if changed_fields == USERNAME:
            buttons[0][0] = InlineKeyboardButton(
                text="Edit Username", callback_data=INPUT_USERNAME
            )
        elif changed_fields == PASSWORD:
            buttons[0][1] = InlineKeyboardButton(
                text="Edit Password", callback_data=INPUT_PASSWORD
            )

    if all(field in user_cache for field in CRED_FIELDS):
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
            InlineKeyboardButton("Yes", callback_data=PROCEED),
            InlineKeyboardButton("No", callback_data=CANCEL),
        ]
    ]


def get_course_name(user_cache: dict[str, str]):
    """Format course name to match input for Course class"""
    assert all(
        field in user_cache for field in FORM_FIELDS
    ), "User cache does not contain all form fields"
    return f"{user_cache[COLLEGE]} {user_cache[DEPARTMENT]}{user_cache[COURSE_NUM]} {user_cache[SECTION]}"


def get_subscription_md(user_cache: dict):
    """Format current subscription form data in markdown"""
    fields = {
        COLLEGE: "College",
        DEPARTMENT: "Department",
        COURSE_NUM: "Course",
        SECTION: "Section",
    }
    result = ""
    for key, label in fields.items():
        result += f"*{label}:*\n"
        if value := user_cache.get(key, ""):
            result += f"{value}\n"
        result += "\n"
    return result


def get_cred_text(user_cache: dict):
    """Format user credentials"""
    username = user_cache.get(USERNAME, "")
    password = user_cache.get(PASSWORD, "")
    masked_password = "*" * len(password)
    privacy_note = "Note: Your credentials are only used to register for courses and are not stored.\n"
    return f"{privacy_note}\nUsername: {username}\nPassword(hidden): {masked_password}"


def recently_subscribed_md(time: str):
    return RECENTLY_SUBSCRIBED_MD.replace("@", time)


def already_subscribed_md(course_name: str):
    return ALREADY_SUBSCRIBED_MD.replace("@", course_name)


def fields_equal(cache1: dict, cache2: dict, fields: set):
    """Check if two user caches have the same form fields"""
    return all(cache1.get(field, None) == cache2.get(field, None) for field in fields)
