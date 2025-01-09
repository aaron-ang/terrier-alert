"""This module contains all the text and buttons used in the bot."""

import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton

from utils.constants import *
from utils.models import Course

load_dotenv()

REPO_URL = os.getenv("REPO_URL")
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
    "*python\-telegram\-bot*, *PyMongo*, and is hosted on *Render*\. "
    f"Check out the code [here]({REPO_URL})\."
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
    base_buttons = [
        [
            ("Input College", InputStates.INPUT_COLLEGE),
            ("Input Department", InputStates.INPUT_DEPARTMENT),
        ],
        [
            ("Input Course", InputStates.INPUT_COURSE_NUM),
            ("Input Section", InputStates.INPUT_SECTION),
        ],
        [("Cancel", InputStates.CANCEL)],
    ]

    buttons = [
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in base_buttons
    ]

    button_mapping = {
        Message.COLLEGE: ("Edit College", 0, 0),
        Message.DEPARTMENT: ("Edit Department", 0, 1),
        Message.COURSE_NUM: ("Edit Course", 1, 0),
        Message.SECTION: ("Edit Section", 1, 1),
    }

    for field, (text, row, col) in button_mapping.items():
        if field in user_cache:
            buttons[row][col] = InlineKeyboardButton(
                text=text,
                callback_data=getattr(InputStates, f"INPUT_{field.name}"),
            )

    if all(field in user_cache for field in FORM_FIELDS):
        buttons.insert(
            -1, [InlineKeyboardButton(text="Submit", callback_data=InputStates.SUBMIT)]
        )

    return buttons


def get_cred_buttons(user_cache: dict):
    """Return user credential buttons"""
    buttons = [
        [
            InlineKeyboardButton(
                text="Input Username", callback_data=InputStates.INPUT_USERNAME
            ),
            InlineKeyboardButton(
                text="Input Password", callback_data=InputStates.INPUT_PASSWORD
            ),
        ],
        [InlineKeyboardButton(text="Cancel", callback_data=InputStates.CANCEL)],
    ]

    for changed_fields in user_cache:
        if changed_fields == Message.USERNAME:
            buttons[0][0] = InlineKeyboardButton(
                text="Edit Username", callback_data=InputStates.INPUT_USERNAME
            )
        elif changed_fields == Message.PASSWORD:
            buttons[0][1] = InlineKeyboardButton(
                text="Edit Password", callback_data=InputStates.INPUT_PASSWORD
            )

    if all(field in user_cache for field in CRED_FIELDS):
        buttons.insert(
            -1, [InlineKeyboardButton(text="Submit", callback_data=InputStates.SUBMIT)]
        )

    return buttons


def get_college_buttons():
    """Return college selection buttons"""
    return [
        [
            InlineKeyboardButton(text=college, callback_data=college)
            for college in COLLEGES[i : i + 3]
        ]
        for i in range(0, len(COLLEGES), 3)
    ]


def get_confirmation_buttons():
    """Return confirmation buttons"""
    return [
        [
            InlineKeyboardButton("Yes", callback_data=InputStates.PROCEED),
            InlineKeyboardButton("No", callback_data=InputStates.CANCEL),
        ]
    ]


def get_course_name(user_cache: dict[str, str]):
    """Format course name to match input for Course class"""
    assert all(
        field in user_cache for field in FORM_FIELDS
    ), "User cache does not contain all form fields"
    return f"{user_cache[Message.COLLEGE]} {user_cache[Message.DEPARTMENT]}{user_cache[Message.COURSE_NUM]} {user_cache[Message.SECTION]}"


def get_subscription_md(user_cache: dict):
    """Format current subscription form data in markdown"""
    fields = {
        Message.COLLEGE: "College",
        Message.DEPARTMENT: "Department",
        Message.COURSE_NUM: "Course",
        Message.SECTION: "Section",
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
    username = user_cache.get(Message.USERNAME, "")
    password = user_cache.get(Message.PASSWORD, "")
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
