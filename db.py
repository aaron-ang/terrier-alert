import os
from datetime import datetime
from pymongo import MongoClient

from course import Course

MONGO_URL = str(os.getenv("MONGO_URL"))

mongo_client = MongoClient(MONGO_URL)
mongo_db = mongo_client["prod_db"]
course_collection = mongo_db["courses"]
user_collection = mongo_db["users"]


def get_all_courses():
    """Find all active courses in database and return iterable of collection objects"""
    return course_collection.find()


def get_user_course(uid: str):
    """Find course which user is subscribed to and return the collection object (dict)"""
    return course_collection.find_one({"users": uid})


def subscribe(course_name: str, uid: str):
    """Update course with new user, inserting new course if necessary"""
    semester = f"{Course.SEMESTER} {Course.YEAR}"
    course_collection.update_one({"name": course_name, "semester": semester},
                                 {"$setOnInsert": {"semester": semester},
                                  "$push": {"users": uid}},
                                 upsert=True)


def unsubscribe(course: str, uid: str):
    """Remove user from course"""
    course_collection.update_one({"name": course},
                                 {"$pull": {"users": uid}})


def remove_course(course: str):
    """Remove course from database"""
    course_collection.delete_one({"name": course})


def get_all_subscribed_users():
    """Find all users in database and return iterable of collection objects"""
    return user_collection.find({"is_subscribed": True})


def get_user(uid: str):
    """Find user in database and return collection object (dict)"""
    return user_collection.find_one({"user": uid})


def update_subscription_time(uid: str, time: datetime):
    """Update user's most recent subscription time"""
    user_collection.update_one({"user": uid},
                               {"$set": {"last_subscribed": time}},
                               upsert=True)


def update_subscription_status(uid: str, is_subscribed: bool):
    """Update user's most recent unsubscription status"""
    user_collection.update_one({"user": uid},
                               {"$set": {"is_subscribed": is_subscribed}},
                               upsert=True)
