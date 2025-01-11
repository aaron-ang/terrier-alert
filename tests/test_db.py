import os
import sys

import pendulum
import pytest
from unittest.mock import MagicMock, patch
from pymongo.errors import PyMongoError
from pymongo.synchronous.database import Database as MongoDB
from pymongo.synchronous.collection import Collection

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import Database
from utils.constants import *
from utils.models import Course


@pytest.fixture
def mock_mongo_client():
    with patch("src.db.MongoClient") as mock_client:
        mock_courses = MagicMock(spec=Collection)
        mock_users = MagicMock(spec=Collection)

        mock_db = MagicMock(spec=MongoDB)
        mock_db.__getitem__.side_effect = lambda x: (
            mock_courses if x == COURSE_LIST else mock_users
        )

        mock_client.return_value.get_database.return_value = mock_db

        yield mock_db


@pytest.fixture
def db(mock_mongo_client):
    database = Database(Environment.DEV)
    database.course_collection = mock_mongo_client[COURSE_LIST]
    database.user_collection = mock_mongo_client[USER_LIST]
    return database


def test_database_init():
    with patch("src.db.MongoClient") as mock_client:
        db = Database(Environment.DEV)
        assert db.env == Environment.DEV
        mock_client.assert_called_once()
        mock_client.return_value.get_database.assert_called_once_with("dev_db")


def test_get_all_courses_empty(db, mock_mongo_client):
    mock_mongo_client[COURSE_LIST].find.return_value = []
    courses = list(db.get_all_courses())
    assert len(courses) == 0
    mock_mongo_client[COURSE_LIST].find.assert_called_once()


def test_get_all_courses_with_data(db, mock_mongo_client):
    expected_courses = [
        {COURSE_NAME: "Course1", USER_LIST: ["user1"]},
        {COURSE_NAME: "Course2", USER_LIST: ["user2", "user3"]},
    ]
    mock_mongo_client[COURSE_LIST].find.return_value = expected_courses

    courses = list(db.get_all_courses())
    assert courses == expected_courses
    assert len(courses[1][USER_LIST]) == 2


def test_get_user_course_not_found(db, mock_mongo_client):
    mock_mongo_client[COURSE_LIST].find_one.return_value = None
    course = db.get_user_course("nonexistent_user")
    assert course is None


def test_get_user_course_found(db, mock_mongo_client):
    test_uid = "test123"
    expected_course = {COURSE_NAME: "Course1", USER_LIST: [test_uid]}
    mock_mongo_client[COURSE_LIST].find_one.return_value = expected_course

    course = db.get_user_course(test_uid)
    assert course == expected_course
    mock_mongo_client[COURSE_LIST].find_one.assert_called_once_with(
        {USER_LIST: test_uid}
    )


def test_subscribe_new_course(db, mock_mongo_client):
    test_course = "CAS CS111 A1"
    test_uid = "test123"
    test_time = pendulum.now()
    test_sem_year = Course.get_sem_year()

    db.subscribe(test_course, test_uid, test_time)

    # Verify course update
    mock_mongo_client[COURSE_LIST].update_one.assert_called_with(
        {COURSE_NAME: test_course, SEM_YEAR: test_sem_year},
        {"$setOnInsert": {SEM_YEAR: test_sem_year}, "$push": {USER_LIST: test_uid}},
        upsert=True,
    )

    # Verify user updates
    mock_mongo_client[USER_LIST].update_one.assert_any_call(
        {UID: test_uid}, {"$set": {LAST_SUBSCRIBED: test_time}}, upsert=True
    )
    mock_mongo_client[USER_LIST].update_one.assert_any_call(
        {UID: test_uid},
        {
            "$set": {
                IS_SUBSCRIBED: True,
                LAST_SUBSCRIPTION: test_course,
            }
        },
        upsert=True,
    )


def test_unsubscribe_existing_user(db, mock_mongo_client):
    test_course = "CAS CS111 A1"
    test_uid = "test123"

    db.unsubscribe(test_course, test_uid)

    # Verify course update
    mock_mongo_client[COURSE_LIST].update_one.assert_called_once_with(
        {COURSE_NAME: test_course}, {"$pull": {USER_LIST: test_uid}}
    )

    # Verify user status update
    mock_mongo_client[USER_LIST].update_one.assert_called_once_with(
        {UID: test_uid},
        {
            "$set": {
                IS_SUBSCRIBED: False,
                LAST_SUBSCRIPTION: test_course,
            }
        },
        upsert=True,
    )


def test_remove_course(db, mock_mongo_client):
    test_course = "CAS CS111 A1"
    mock_mongo_client[COURSE_LIST].delete_one.return_value.deleted_count = 1

    result = db.remove_course(test_course)
    assert result.deleted_count == 1
    mock_mongo_client[COURSE_LIST].delete_one.assert_called_once_with(
        {COURSE_NAME: test_course}
    )


def test_get_user_nonexistent(db, mock_mongo_client):
    mock_mongo_client[USER_LIST].find_one.return_value = None
    user = db.get_user("nonexistent_user")
    assert user is None


def test_update_subscription_time(db, mock_mongo_client):
    test_uid = "test123"
    test_time = pendulum.now()

    db.update_subscription_time(test_uid, test_time)
    mock_mongo_client[USER_LIST].update_one.assert_called_once_with(
        {UID: test_uid}, {"$set": {LAST_SUBSCRIBED: test_time}}, upsert=True
    )


def test_update_subscription_status(db, mock_mongo_client):
    test_uid = "test123"
    test_course = "CAS CS111 A1"

    db.update_subscription_status(test_uid, test_course, True)
    mock_mongo_client[USER_LIST].update_one.assert_called_once_with(
        {UID: test_uid},
        {
            "$set": {
                IS_SUBSCRIBED: True,
                LAST_SUBSCRIPTION: test_course,
            }
        },
        upsert=True,
    )


def test_database_error_handling():
    with patch("src.db.MongoClient") as mock_client:
        mock_client.side_effect = PyMongoError("Connection failed")
        with pytest.raises(PyMongoError):
            Database(Environment.DEV)
