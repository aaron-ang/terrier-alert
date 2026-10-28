from dotenv import load_dotenv

from src.db import Database
from utils.constants import COURSE_NAME, LAST_SUBSCRIPTION, UID, USER_LIST, Environment


def update(env: Environment):
    load_dotenv()
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
