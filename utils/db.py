"""Database interface for the course subscription system."""

import os
from typing import Optional, Iterator

import pendulum
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

from utils.models import Course
from utils.constants import *

load_dotenv()


class Database:
    def __init__(self, env: str) -> None:
        mongo_client = MongoClient(os.getenv("MONGO_URL"), tlsCAFile=certifi.where())
        mongo_db = mongo_client.get_database(f"{env}_db")
        self.env = env
        self.course_collection = mongo_db["courses"]
        self.user_collection = mongo_db["users"]

    def get_all_courses(self) -> Iterator[dict]:
        return self.course_collection.find()

    def get_user_course(self, uid: str) -> Optional[dict]:
        return self.course_collection.find_one({USER_LIST: uid})

    def subscribe(
        self, course_name: str, uid: str, subscription_time: pendulum.DateTime
    ) -> None:
        """Update course with new user, inserting new course if necessary"""
        sem_year = Course.get_sem_year()
        self.course_collection.update_one(
            {COURSE_NAME: course_name, SEM_YEAR: sem_year},
            {"$setOnInsert": {SEM_YEAR: sem_year}, "$push": {USER_LIST: uid}},
            upsert=True,
        )
        self.update_subscription_time(uid, subscription_time)
        self.update_subscription_status(uid, course_name, True)

    def unsubscribe(self, course_name: str, uid: str) -> None:
        """Remove user from course"""
        self.course_collection.update_one(
            {COURSE_NAME: course_name}, {"$pull": {USER_LIST: uid}}
        )
        self.update_subscription_status(uid, course_name, False)

    def remove_course(self, course_name: str) -> None:
        """Remove course from database"""
        return self.course_collection.delete_one({COURSE_NAME: course_name})

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
        self, uid: str, course_name: str, is_subscribed: bool
    ) -> None:
        """Update user's subscription status."""
        self.user_collection.update_one(
            {UID: uid},
            {
                "$set": {
                    IS_SUBSCRIBED: is_subscribed,
                    LAST_SUBSCRIPTION: course_name,
                }
            },
            upsert=True,
        )
