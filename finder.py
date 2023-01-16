import os
import time
import asyncio
import telegram
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import db
from course import Course

options = webdriver.ChromeOptions()
options.binary_location = str(os.getenv("GOOGLE_CHROME_BIN"))
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-gpu')
options.add_argument('--disable-dev-shm-usage')

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))
COURSE_MAP: dict[Course, list[str]] = {}
COURSES_TO_REMOVE: list[Course] = []

driver = webdriver.Chrome(executable_path=str(
    os.getenv("CHROMEDRIVER_PATH")), options=options)
wait = WebDriverWait(driver, timeout=30)
bot = telegram.Bot(token=BOT_TOKEN)


async def search_courses():
    for course in db.find_all_courses():
        users = list(course["users"])
        # prune courses with no users
        if len(users) == 0:
            COURSES_TO_REMOVE.append(Course(course["name"]))
        else:
            COURSE_MAP[Course(course["name"])] = users

    for course in COURSE_MAP:
        driver.get(course.bin_url)
        try:
            # wait until elements are rendered
            wait.until(EC.visibility_of_element_located(
                (By.XPATH, "/html/body/table[4]/tbody")))
            await process_course(course)
        except:
            break


async def process_course(course: Course):
    # check for pinned message
    PINNED_XPATH = "/html/body/table[4]/tbody/tr[2]/td[1]/font/table/tbody/tr/td[1]/img"
    RESULT_XPATH = "/html/body/table[4]/tbody/tr[3]" if driver.find_elements(
        By.XPATH, PINNED_XPATH) else "/html/body/table[4]/tbody/tr[2]"

    keywords = ["Class Full"]
    try:
        # check validity of class
        course_name = driver.find_element(
            By.XPATH, RESULT_XPATH + "/td[2]/font/a").text

        if course_name != str(course):
            msg = f"{str(course)} is not available. Did you mean {course_name}?"
            await notify_users(course, msg)
            return

        class_remark = driver.find_element(
            By.XPATH, RESULT_XPATH + "/td[13]/font").text
        if class_remark == "Class Closed":
            msg = f"{str(course)} is closed. Please join the course waitlist or contact your instructor."
            await notify_users(course, msg)
            return

        num_seats = driver.find_element(
            By.XPATH, RESULT_XPATH + "/td[7]/font").text
        is_blocked = class_remark in keywords
        is_avail = int(num_seats) > 0 and not is_blocked

        if is_avail:
            msg = f"{str(course)} is now available at {course.reg_url}"
            await notify_users(course, msg)

    except Exception:
        return


async def notify_users(course: Course, msg: str):
    for uid in COURSE_MAP[course]:
        await bot.send_message(uid, msg)
    COURSES_TO_REMOVE.append(course)


async def main():
    # Scrape website every minute
    while True:
        await search_courses()

        for course in COURSES_TO_REMOVE:
            db.remove_course(str(course))
            if course in COURSE_MAP:
                COURSE_MAP.pop(course)
        COURSES_TO_REMOVE.clear()

        time.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
