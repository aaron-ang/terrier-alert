import os
import time
import asyncio
import telegram
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from dotenv import load_dotenv

from course import Course
import db

load_dotenv()

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))
FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
COURSE_MAP: dict[Course, list[str]] = {}
COURSES_TO_REMOVE: list[Course] = []
TIMEOUT_SECONDS = 5

options = webdriver.ChromeOptions()
options.binary_location = str(os.getenv("GOOGLE_CHROME_BIN"))
options.add_argument("--no-sandbox")
options.add_argument("--headless")
options.add_argument("disable-infobars")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(executable_path=os.getenv("CHROMEDRIVER_PATH")),
    options=options,
)
wait = WebDriverWait(driver, timeout=30)
bot = telegram.Bot(token=BOT_TOKEN)


async def search_courses():
    for course_doc in db.get_all_courses():
        users = list(course_doc["users"])
        course = Course(course_doc["name"])
        semester = course_doc["semester"]

        if len(users) == 0:  # prune courses with no users
            COURSES_TO_REMOVE.append(course)
            continue
        else:
            COURSE_MAP[course] = users

        if semester != f"{Course.get_semester()} {Course.get_year()}":
            await notify_users_and_remove_course(
                course,
                f"You have been unsubscribed from {course} since {semester} is almost over.",
            )
            COURSE_MAP.pop(course)

    for course in COURSE_MAP:
        driver.get(course.bin_url)
        wait.until(
            EC.visibility_of_element_located((By.XPATH, "/html/body/table[4]/tbody"))
        )
        await process_course(course)


async def process_course(course: Course):
    # Check for pinned message
    PINNED_XPATH = "/html/body/table[4]/tbody/tr[2]/td[1]/font/table/tbody/tr/td[1]/img"
    RESULT_XPATH = f"/html/body/table[4]/tbody/tr[{'3' if driver.find_elements(By.XPATH, PINNED_XPATH) else '2'}]"
    keywords = ["Class Closed", "WebReg Restricted"]

    # Check validity of class
    course_name = driver.find_element(By.XPATH, RESULT_XPATH + "/td[2]/font/a").text
    if course_name != str(course):
        msg = f"{str(course)} is not available. Did you mean {course_name}?"
        await notify_users_and_remove_course(course, msg)
        return

    class_remark = driver.find_element(By.XPATH, RESULT_XPATH + "/td[13]/font").text
    if any([kw for kw in keywords if kw in class_remark]):
        msg = f"Registration for {str(course)} is restricted. Please join the course waitlist or contact your instructor."
        await notify_users_and_remove_course(course, msg)
        return

    num_seats = driver.find_element(By.XPATH, RESULT_XPATH + "/td[7]/font").text
    is_full = "Class Full" in class_remark
    is_avail = not is_full and int(num_seats) > 0

    if is_avail:
        msg = f"{str(course)} is now available at {course.reg_url}"
        await notify_users_and_remove_course(course, msg)


async def notify_users_and_remove_course(course: Course, msg: str):
    for uid in COURSE_MAP[course]:
        await bot.send_message(uid, msg, write_timeout=TIMEOUT_SECONDS)
        db.update_subscription_status(uid, False)
    COURSES_TO_REMOVE.append(course)


async def notify_admin(msg: str):
    await bot.send_message(FEEDBACK_CHANNEL_ID, msg, write_timeout=TIMEOUT_SECONDS)


def driver_alive():
    try:
        if not driver.service.is_connectable():
            return False
        driver.service.assert_process_still_running()
    except WebDriverException:
        return False
    return True


async def main():
    while True:
        try:
            if not driver_alive():
                return
            await search_courses()
            while COURSES_TO_REMOVE:
                course = COURSES_TO_REMOVE.pop()
                db.remove_course(str(course))
            COURSE_MAP.clear()
            time.sleep(60)

        except Exception as e:
            await notify_admin(repr(e))


if __name__ == "__main__":
    print("Starting finder...")
    asyncio.run(main())
