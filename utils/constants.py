from enum import Enum, StrEnum


class Environment(StrEnum):
    PROD = "prod"
    DEV = "dev"


class TimeConstants(Enum):
    REFRESH_TIME_HOURS = 24
    TIMEOUT_SECONDS = 5


class InputStates(Enum):
    AWAIT_SELECTION = 1
    AWAIT_CUSTOM_INPUT = 2
    AWAIT_INPUT_USERNAME = 3
    AWAIT_INPUT_PASSWORD = 4
    AWAIT_FEEDBACK = 5
    INPUT_COLLEGE = 6
    INPUT_DEPARTMENT = 7
    INPUT_COURSE_NUM = 8
    INPUT_SECTION = 9
    INPUT_USERNAME = 10
    INPUT_PASSWORD = 11
    SUBMIT = 12
    PROCEED = 13
    CANCEL = 14


class Message(Enum):
    COLLEGE = 1
    DEPARTMENT = 2
    COURSE_NUM = 3
    SECTION = 4
    USERNAME = 5
    PASSWORD = 6
    IS_SUBSCRIBED = 7
    LAST_SUBSCRIBED = 8
    LAST_SUBSCRIPTION = 9
    SUBSCRIPTION_MSG_ID = 10
    PROMPT_MSG_ID = 11
    INVALID_MSG_ID = 12
    CRED_MSG_ID = 13


FORM_FIELDS = {
    Message.COLLEGE,
    Message.DEPARTMENT,
    Message.COURSE_NUM,
    Message.SECTION,
}

CRED_FIELDS = {Message.USERNAME, Message.PASSWORD}

UID = "user"
USER_LIST = "users"
COURSE_NAME = "name"
SEM_YEAR = "semester"
IS_SUBSCRIBED = "is_subscribed"
LAST_SUBSCRIBED = "last_subscribed"
LAST_SUBSCRIPTION = "last_subscription"
