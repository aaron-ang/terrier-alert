"""Database interface for the course subscription system."""

import os
import sys
from typing import Optional, Iterator

import pendulum
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.models import Course
from utils.constants import (
    Environment,
    COURSE_LIST,
    USER_LIST,
    COURSE_NAME,
    SEM_YEAR,
    UID,
    LAST_SUBSCRIBED,
    IS_SUBSCRIBED,
    LAST_SUBSCRIPTION,
)

load_dotenv()


class Database:
    def __init__(self, env: Environment):
        mongo_client = MongoClient(os.getenv("MONGO_URL"), tlsCAFile=certifi.where())
        mongo_db = mongo_client.get_database(f"{env}_db")
        self.env = env
        self.course_collection = mongo_db[COURSE_LIST]
        self.user_collection = mongo_db[USER_LIST]

    def get_all_courses(self) -> Iterator[dict]:
        return self.course_collection.find()

    def get_user_course(self, uid: str) -> Optional[dict]:
        return self.course_collection.find_one({USER_LIST: uid})

    def subscribe(
        self, course: Course, uid: str, subscription_time: pendulum.DateTime
    ) -> None:
        """Update course with new user, inserting new course if necessary"""
        course_name = str(course)
        sem_year = Course.get_sem_year()
        self.course_collection.update_one(
            {COURSE_NAME: course_name, SEM_YEAR: sem_year},
            {"$setOnInsert": {SEM_YEAR: sem_year}, "$push": {USER_LIST: uid}},
            upsert=True,
        )
        self.update_subscription_time(uid, subscription_time)
        self.update_subscription_status(uid, course_name, True)

    def unsubscribe(self, course: Course, uid: str) -> None:
        """Remove user from course"""
        course_name = str(course)
        self.course_collection.update_one(
            {COURSE_NAME: course_name}, {"$pull": {USER_LIST: uid}}
        )
        self.update_subscription_status(uid, course_name, False)

    def remove_course(self, course: Course) -> None:
        """Remove course from database"""
        return self.course_collection.delete_one({COURSE_NAME: str(course)})

    def get_all_users(self) -> Iterator[dict]:
        """Find all users in database and return iterable of collection objects"""
        return self.user_collection.find()

    def get_user(self, uid: str) -> Optional[dict]:
        """Find user in database and return collection object (dict)"""
        return self.user_collection.find_one({UID: uid})

    def update_subscription_time(self, uid: str, time: pendulum.DateTime) -> None:
        """Update user's last subscription timestamp."""
        self.user_collection.update_one(
            {UID: uid}, {"$set": {LAST_SUBSCRIBED: time}}, upsert=True
        )

    def update_subscription_status(
        self, uid: str, last_subscribed: str, is_subscribed: bool
    ) -> None:
        """Update user's subscription status."""
        self.user_collection.update_one(
            {UID: uid},
            {
                "$set": {
                    IS_SUBSCRIBED: is_subscribed,
                    LAST_SUBSCRIPTION: last_subscribed,
                }
            },
            upsert=True,
        )
