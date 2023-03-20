import os
import time
import asyncio
import telegram
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

import db
from course import Course


options = webdriver.ChromeOptions()
options.binary_location = str(os.getenv("GOOGLE_CHROME_BIN"))
options.add_argument('--no-sandbox')
options.add_argument('--headless')
options.add_argument('disable-infobars')
options.add_argument('--disable-dev-shm-usage')

BOT_TOKEN = str(os.getenv("TELEGRAM_TOKEN"))
COURSE_MAP: dict[Course, list[str]] = {}
COURSES_TO_REMOVE: list[Course] = []
TIMEOUT_SECONDS = 5

driver = webdriver.Chrome(service=Service(executable_path=str(os.getenv("CHROMEDRIVER_PATH"))),
                          options=options)
wait = WebDriverWait(driver, timeout=30)
bot = telegram.Bot(token=BOT_TOKEN)


async def search_courses():
    for course in db.get_all_courses():
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

    keywords = ["Class Closed", "WebReg Restricted"]
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
        if any([kw for kw in keywords if kw in class_remark]):
            msg = f"Registration for {str(course)} is restricted. Please join the course waitlist or contact your instructor."
            await notify_users(course, msg)
            return

        num_seats = driver.find_element(
            By.XPATH, RESULT_XPATH + "/td[7]/font").text
        is_full = "Class Full" in class_remark
        is_avail = not is_full and int(num_seats) > 0

        if is_avail:
            msg = f"{str(course)} is now available at {course.reg_url}"
            await notify_users(course, msg)

    except Exception:
        return


async def notify_users(course: Course, msg: str):
    for uid in COURSE_MAP[course]:
        await bot.send_message(uid, msg, write_timeout=TIMEOUT_SECONDS)
        db.update_subscription_status(uid, False)
    COURSES_TO_REMOVE.append(course)


async def main():
    while True:
        await search_courses()

        while COURSES_TO_REMOVE:
            course = COURSES_TO_REMOVE.pop()
            db.remove_course(str(course))
        
        COURSE_MAP.clear()

        time.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
