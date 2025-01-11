import sys

sys.path.append("./")
from src.db import Database
from src.bot import Environment
from utils.constants import UID, USER_LIST, COURSE_NAME, LAST_SUBSCRIPTION


def update(env: Environment):
    database = Database(env)

    for course in database.get_all_courses():
        for user in course[USER_LIST]:
            database.update_subscription_status(user, course[COURSE_NAME], True)

    for user in database.get_all_users():
        if LAST_SUBSCRIPTION not in user:
            database.update_subscription_status(user[UID], "", False)


if __name__ == "__main__":
    try:
        update(Environment.DEV)
    except Exception as e:
        print(e)
    else:
        print("Data updated successfully!")
