import os
import sys
import time
import asyncio
import telegram
import pendulum
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import DEV, PROD, TIMEOUT_SECONDS
from utils.course import Course
from utils.db import Database

load_dotenv()

FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))


async def search_courses():
    """Iterate through and process a snapshot of course subscriptions."""
    for course_doc in DB.get_all_courses():
        course = Course(course_doc["name"])
        users = list(course_doc["users"])
        if len(users) == 0:  # prune courses with no users
            DB.remove_course(str(course))
            continue

        semester = course_doc["semester"]
        if semester != Course.get_sem_year():
            msg = (
                f"You have been unsubscribed from {course} "
                f"since the deadline to add courses for {semester} has passed."
            )
            await notify_users_and_unsubscribe(course, msg, users)
            continue

        await process_course(course, users)


async def process_course(course: Course, users: list[str]):
    """Checks for edge cases and course availability. Handles notifications for each case."""
    DRIVER.get(course.bin_url)
    WAIT.until(
        EC.visibility_of_element_located((By.XPATH, "/html/body/table[4]/tbody"))
    )

    # Check for pinned message
    pinned_xpath = "/html/body/table[4]/tbody/tr[2]/td[1]/font/table/tbody/tr/td[1]/img"
    result_row_index = 3 if DRIVER.find_elements(By.XPATH, pinned_xpath) else 2
    result_xpath = f"/html/body/table[4]/tbody/tr[{result_row_index}]"

    # Check validity of course
    course_name = DRIVER.find_element(By.XPATH, result_xpath + "/td[2]/font/a").text
    if course_name != str(course):
        msg = f"{str(course)} was not found in the University Class Schedule. Did you mean {course_name}?"
        await notify_users_and_unsubscribe(course, msg, users)
        return

    if course_available(result_xpath, course_name):
        msg = f"{str(course)} is now available at {course.reg_url}"
        await notify_users_and_unsubscribe(course, msg, users)


def course_available(result_xpath: str, course_name: str):
    keywords = ["Class Closed", "WebReg Restricted"]
    course_remark = DRIVER.find_element(By.XPATH, result_xpath + "/td[13]/font").text

    # Edge case: lecture not flagged but discussion is
    next_course_xpath = get_next_course_xpath(result_xpath)
    next_course_name = DRIVER.find_element(
        By.XPATH, next_course_xpath + "/td[2]/font/a"
    ).text
    if next_course_name.split()[0] == course_name.split()[0]:
        next_course_remark = DRIVER.find_element(
            By.XPATH, next_course_xpath + "/td[13]/font"
        ).text
        course_remark += f" {next_course_remark}"

    if any(filter(lambda kw: kw in course_remark, keywords)):
        return False

    num_seats = DRIVER.find_element(By.XPATH, result_xpath + "/td[7]/font").text
    is_full = "Class Full" in course_remark
    is_avail = not is_full and int(num_seats) > 0
    return is_avail


def get_next_course_xpath(result_xpath: str):
    row_index = int(result_xpath.split("[")[-1].split("]")[0])
    result_xpath = result_xpath.replace(f"/tr[{row_index}]", f"/tr[{row_index + 1}]")
    while not DRIVER.find_element(By.XPATH, result_xpath + "/td[2]/font/a").text:
        result_xpath = result_xpath.replace(
            f"/tr[{row_index}]", f"/tr[{row_index + 1}]"
        )
        row_index += 1
    return result_xpath


async def notify_users_and_unsubscribe(course: Course, msg: str, users: list[str]):
    """Notifies each user on Telegram and unsubscribes them from the course."""
    for uid in users:
        await BOT.send_message(uid, msg, write_timeout=TIMEOUT_SECONDS)
        DB.unsubscribe(str(course), uid)


async def notify_admin(msg: str):
    """Sends a notification to Telegram feedback channel."""
    await BOT.send_message(FEEDBACK_CHANNEL_ID, msg, write_timeout=TIMEOUT_SECONDS)


def driver_alive():
    """Checks if the driver is still alive."""
    try:
        if not DRIVER.service.is_connectable():
            return False

        DRIVER.service.assert_process_still_running()
        return True

    except WebDriverException:
        return False


async def main(env=PROD):
    """Runs the finder every minute."""
    print("Starting finder...")
    global BOT, DB, DRIVER, WAIT

    bot_token = os.getenv("TELEGRAM_TOKEN" if env == PROD else "TEST_TELEGRAM_TOKEN")
    BOT = telegram.Bot(token=bot_token)
    DB = Database(env)

    options = webdriver.ChromeOptions()
    if bin_path := os.getenv("GOOGLE_CHROME_BIN"):
        options.binary_location = bin_path
        options.add_argument("--start-maximized")
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    DRIVER = webdriver.Chrome(
        service=Service(
            executable_path=os.getenv("CHROMEDRIVER_PATH")
            if env == PROD
            else ChromeDriverManager().install()
        ),
        options=options,
    )
    WAIT = WebDriverWait(DRIVER, timeout=30)

    timeout = None
    while True:
        try:
            if not driver_alive():
                return
            await search_courses()

        except TimeoutException:
            if not timeout:
                timeout = pendulum.now()
            else:
                minutes_since_last_timeout = pendulum.now().diff(timeout).in_minutes()
                if minutes_since_last_timeout % 20 == 0:
                    await notify_admin(
                        f"Finder timed out for {minutes_since_last_timeout} minutes."
                    )

        except Exception as exc:
            await notify_admin(repr(exc))

        else:
            timeout = None

        finally:
            time.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
