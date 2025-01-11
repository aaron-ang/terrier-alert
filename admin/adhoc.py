import sys

sys.path.append("./")
from src.db import Database
from src.bot import Environment


def update(env: Environment):
    database = Database(env)

    for course in database.get_all_courses():
        for user in course["users"]:
            database.update_subscription_status(user, course["name"], True)

    for user in database.get_all_users():
        if "last_subscription" not in user:
            database.update_subscription_status(user["user"], "", False)


if __name__ == "__main__":
    try:
        update(Environment.DEV)
    except Exception as e:
        print(e)
    else:
        print("Data updated successfully!")
