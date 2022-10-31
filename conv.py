from telegram import InlineKeyboardButton

(
    AWAIT_SELECTION,
    INPUT_COLLEGE,
    INPUT_DEPARTMENT,
    INPUT_COURSE_NUM,
    INPUT_SECTION,
    SUBMIT,
    CANCEL
) = map(chr, range(7))

(
    COLLEGE,
    DEPARTMENT,
    COURSE_NUM,
    SECTION,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED
) = map(chr, range(6))

COLLEGES = ["CAS", "CDS", "COM", "ENG", "SAR", "QST"]
NOT_SUBSCRIBED_TEXT = "You are not subscribed to any course. Use /subscribe to start a subscription."
UNSUBSCRIBE_TEXT = "You can only resubscribe 24 hours after your last subscription. Are you sure you want to unsubscribe?"


def get_main_buttons(user_cache: dict):
    buttons = [
        [
            InlineKeyboardButton(text="Input College",
                                 callback_data=INPUT_COLLEGE),
            InlineKeyboardButton(text="Input Department",
                                 callback_data=INPUT_DEPARTMENT),
        ],
        [
            InlineKeyboardButton(text="Input Course",
                                 callback_data=INPUT_COURSE_NUM),
            InlineKeyboardButton(text="Input Section",
                                 callback_data=INPUT_SECTION),
        ],
        [InlineKeyboardButton(text="Cancel", callback_data=CANCEL)]
    ]

    if not user_cache:
        return buttons

    for changed_fields in user_cache:
        if changed_fields == COLLEGE:
            buttons[0][0] = InlineKeyboardButton(
                text="Edit College",
                callback_data=INPUT_COLLEGE
            )
        elif changed_fields == DEPARTMENT:
            buttons[0][1] = InlineKeyboardButton(
                text="Edit Department",
                callback_data=INPUT_DEPARTMENT
            )
        elif changed_fields == COURSE_NUM:
            buttons[1][0] = InlineKeyboardButton(
                text="Edit Course",
                callback_data=INPUT_COURSE_NUM
            )
        elif changed_fields == SECTION:
            buttons[1][1] = InlineKeyboardButton(
                text="Edit Section",
                callback_data=INPUT_SECTION
            )

    if len(dict(user_cache)) == 6:
        buttons.insert(2, [InlineKeyboardButton(
            text="Submit", callback_data=SUBMIT)])

    return buttons


def get_college_buttons():
    return [
        [InlineKeyboardButton(text=college, callback_data=college)
         for college in COLLEGES[:3]],
        [InlineKeyboardButton(text=college, callback_data=college)
         for college in COLLEGES[3:]],
    ]


def get_unsubscribe_buttons():
    return [[InlineKeyboardButton("Yes", callback_data=SUBMIT),
             InlineKeyboardButton("No", callback_data=CANCEL)]]


def get_subscription_text(user_cache: dict):
    college = "" if not user_cache.get(
        COLLEGE) else user_cache[COLLEGE] + "\n"
    department = "" if not user_cache.get(
        DEPARTMENT) else user_cache[DEPARTMENT] + "\n"
    course_num = "" if not user_cache.get(
        COURSE_NUM) else user_cache[COURSE_NUM] + "\n"
    section = "" if not user_cache.get(SECTION) else user_cache[SECTION]

    return (
        f"*College:*\n{college}\n"
        f"*Department:*\n{department}\n"
        f"*Course:*\n{course_num}\n"
        f"*Section:*\n{section}"
    )
