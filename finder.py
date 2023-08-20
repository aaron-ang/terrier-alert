import os
import time
import asyncio
import telegram
import pendulum
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

from course import Course
import db

load_dotenv()

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))
FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
TIMEOUT_SECONDS = 5

options = webdriver.ChromeOptions()
options.binary_location = str(os.getenv("GOOGLE_CHROME_BIN"))
options.add_argument("--no-sandbox")
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(
    service=Service(executable_path=os.getenv("CHROMEDRIVER_PATH")),
    options=options,
)
wait = WebDriverWait(driver, timeout=30)
bot = telegram.Bot(token=BOT_TOKEN)


async def search_courses():
    """Iterate through and process a snapshot of course subscriptions."""
    for course_doc in db.get_all_courses():
        course = Course(course_doc["name"])
        users = list(course_doc["users"])
        if len(users) == 0:  # prune courses with no users
            db.remove_course(str(course))
            continue

        semester = course_doc["semester"]
        if semester != f"{Course.get_semester()} {Course.get_year()}":
            msg = f"You have been unsubscribed from {course} since {semester} is almost over."
            await notify_users_and_unsubscribe(course, msg, users)
            continue

        await process_course(course, users)


async def process_course(course: Course, users: list[str]):
    """Checks for edge cases and course availability. Handles notifications for each case."""
    driver.get(course.bin_url)
    wait.until(
        EC.visibility_of_element_located((By.XPATH, "/html/body/table[4]/tbody"))
    )

    # Check for pinned message
    pinned_xpath = "/html/body/table[4]/tbody/tr[2]/td[1]/font/table/tbody/tr/td[1]/img"
    result_row_index = 3 if driver.find_elements(By.XPATH, pinned_xpath) else 2
    result_xpath = f"/html/body/table[4]/tbody/tr[{result_row_index}]"
    keywords = ["Class Closed", "WebReg Restricted"]

    # Check validity of class
    course_name = driver.find_element(By.XPATH, result_xpath + "/td[2]/font/a").text
    if course_name != str(course):
        msg = f"{str(course)} is not available. Did you mean {course_name}?"
        await notify_users_and_unsubscribe(course, msg, users)
        return

    class_remark = driver.find_element(By.XPATH, result_xpath + "/td[13]/font").text
    if any(filter(lambda kw: kw in class_remark, keywords)):
        msg = (
            f"Registration for {str(course)} is restricted. "
            "Please join the course waitlist or contact your instructor."
        )
        await notify_users_and_unsubscribe(course, msg, users)
        return

    num_seats = driver.find_element(By.XPATH, result_xpath + "/td[7]/font").text
    is_full = "Class Full" in class_remark
    is_avail = not is_full and int(num_seats) > 0

    if is_avail:
        msg = f"{str(course)} is now available at {course.reg_url}"
        await notify_users_and_unsubscribe(course, msg, users)


async def notify_users_and_unsubscribe(course: Course, msg: str, users: list[str]):
    """Notifies each user on Telegram and unsubscribes them from the course."""
    for uid in users:
        await bot.send_message(uid, msg, write_timeout=TIMEOUT_SECONDS)
        db.unsubscribe(str(course), uid)
        db.update_subscription_status(uid, False)


async def notify_admin(msg: str):
    """Sends a notification to Telegram feedback channel."""
    await bot.send_message(FEEDBACK_CHANNEL_ID, msg, write_timeout=TIMEOUT_SECONDS)


def driver_alive():
    """Checks if the driver is still alive."""
    try:
        if not driver.service.is_connectable():
            return False

        driver.service.assert_process_still_running()

        return True

    except WebDriverException:
        return False


async def main():
    """Runs the finder every minute."""
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
    print("Starting finder...")
    asyncio.run(main())
