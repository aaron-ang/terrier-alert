"""Database interface for the course subscription system."""

import os
from collections.abc import Iterator
from typing import Any

import certifi
import pendulum
from pymongo import MongoClient

from utils.constants import (
    COURSE_LIST,
    COURSE_NAME,
    IS_SUBSCRIBED,
    LAST_SUBSCRIBED,
    LAST_SUBSCRIPTION,
    SEM_YEAR,
    UID,
    USER_LIST,
    Environment,
)
from utils.models import Course, get_sem_year


class Database:
    def __init__(self, env: Environment):
        mongo_client: MongoClient[dict[str, Any]] = MongoClient(
            os.getenv("MONGO_URL"), tlsCAFile=certifi.where()
        )
        mongo_db = mongo_client.get_database(f"{env}_db")
        self.env = env
        self.course_collection = mongo_db[COURSE_LIST]
        self.user_collection = mongo_db[USER_LIST]

    def get_all_courses(self) -> Iterator[dict]:
        return self.course_collection.find()

    def get_user_course(self, uid: str) -> dict | None:
        return self.course_collection.find_one({USER_LIST: uid})

    def subscribe(
        self, course: Course, uid: str, subscription_time: pendulum.DateTime
    ) -> None:
        """Update course with new user, inserting new course if necessary"""
        course_name = str(course)
        sem_year = get_sem_year()
        self.course_collection.update_one(
            {COURSE_NAME: course_name, SEM_YEAR: sem_year},
            {"$setOnInsert": {SEM_YEAR: sem_year}, "$addToSet": {USER_LIST: uid}},
            upsert=True,
        )
        self.update_subscription_time(uid, subscription_time)
        self.update_subscription_status(uid, course_name, True)

    def unsubscribe(self, course: Course, uid: str) -> None:
        """Remove user from course in every semester it is listed under"""
        course_name = str(course)
        self.course_collection.update_many(
            {COURSE_NAME: course_name, USER_LIST: uid}, {"$pull": {USER_LIST: uid}}
        )
        self.update_subscription_status(uid, course_name, False)

    def remove_course(self, course: Course, semester: str) -> None:
        """Remove a course with no subscribers from database"""
        self.course_collection.delete_one(
            {COURSE_NAME: str(course), SEM_YEAR: semester, USER_LIST: {"$size": 0}}
        )

    def get_all_users(self) -> Iterator[dict]:
        """Find all users in database and return iterable of collection objects"""
        return self.user_collection.find()

    def get_user(self, uid: str) -> dict | None:
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
