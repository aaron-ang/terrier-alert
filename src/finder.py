import os
import sys
import time
import pendulum
from dotenv import load_dotenv
from telegram import constants, CallbackQuery
from telegram.ext import ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import *
from utils.course import Course
from utils.db import Database


load_dotenv()

FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
REG_TITLE = "Add Classes - Display"
REG_OPT = "Registration Options"
REG_CFM = "Add Classes - Confirmation"
DRIVER: webdriver.Chrome = None
timeout: pendulum.DateTime = None


async def register_course(env: str, user_cache: dict, query: CallbackQuery):
    """Regiser a course for the user, to be called by `bot.py`"""
    # Create one driver per task
    driver, wait = init_driver(env, wait_timeout=10)
    course_name = user_cache.get(LAST_SUBSCRIPTION, "")
    assert course_name, "No course to register."
    course = Course(course_name)

    # Login
    await query.edit_message_text("Signing you in...")
    driver.get(course.reg_url)
    wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, """//*[@id="wrapper"]/div/form/fieldset""")
        )
    )
    username_box = driver.find_element(By.ID, "j_username")
    password_box = driver.find_element(By.ID, "j_password")
    login_button = driver.find_element(By.NAME, "_eventId_proceed")
    username, password = user_cache.get(USERNAME, ""), user_cache.get(PASSWORD, "")
    assert username and password, "No username or password found."
    username_box.send_keys(username)
    password_box.send_keys(password)
    login_button.click()

    login_error_xpath = """//*[@id="wrapper"]/div/div[1]"""
    if driver.find_elements(By.XPATH, login_error_xpath):
        await query.edit_message_text("Invalid login credentials. Please try again.")
        time.sleep(1)
        raise ValueError

    await query.edit_message_text("Awaiting DUO authentication...")
    dont_trust_button: WebElement = wait.until(
        EC.visibility_of_element_located((By.ID, "dont-trust-browser-button"))
    )
    dont_trust_button.click()

    # Check validity of course
    await query.edit_message_text("Registering for the course...")
    wait.until(EC.title_is(REG_TITLE))
    pinned_xpath = "/html/body/form/table[1]/tbody/tr[2]/td[2]/table/tbody/tr/td[1]/img"
    result_row_index = 3 if driver.find_elements(By.XPATH, pinned_xpath) else 2
    result_xpath = f"/html/body/form/table[1]/tbody/tr[{result_row_index}]"
    input_xpath = result_xpath + "/td[1]/input"
    if not driver.find_elements(By.XPATH, input_xpath):
        await query.edit_message_text(
            f"{course_name} is not available. Use /resubscribe to get notified when it is."
        )
        return

    # Hack to handle semester mismatch screen
    driver.find_element(By.XPATH, "/html/body/table[2]/tbody/tr/td[2]/a").click()
    wait.until(EC.title_is(REG_OPT))
    driver.get(course.reg_url)
    wait.until(EC.title_is(REG_TITLE))

    # Register
    input = driver.find_element(By.XPATH, input_xpath)
    add_class_btn = driver.find_element(
        By.XPATH, "/html/body/form/center[2]/table/tbody/tr/td[1]/input"
    )
    input.click()
    add_class_btn.click()

    alert: Alert = wait.until(EC.alert_is_present())
    alert.accept()

    wait.until(EC.title_is(REG_CFM))
    cfm_img = driver.find_element(By.XPATH, "/html/body/table[4]/tbody/tr[2]/td[1]/img")
    if "checkmark" in cfm_img.get_attribute("src"):
        await query.edit_message_text(f"Successfully registered for {course_name}!")
    else:
        await query.edit_message_text(
            f"Failed to register for {course_name}\. Register manually [here]({course.reg_option_url})\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )
    driver.quit()


async def search_courses():
    """Iterate through and process a snapshot of course subscriptions."""
    for course_doc in DB.get_all_courses():
        course = Course(course_doc["name"])
        users = list(course_doc["users"])
        if len(users) == 0:  # prune courses with no users
            DB.remove_course(course.get_course_name())
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
    course_name_web = DRIVER.find_element(By.XPATH, result_xpath + "/td[2]/font/a").text
    course_name_db = course.get_course_name()
    if course_name_db != course_name_web:
        msg = f"{course_name_db} was not found in the University Class Schedule. Did you mean {course_name_web}?"
        await notify_users_and_unsubscribe(course, msg, users)
    elif course_available(result_xpath, course_name_db):
        msg = f"{course_name_db} is now available! Use /register to add it to your schedule."
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
        if kw_present(keywords, next_course_remark):
            return False

    if kw_present(keywords, course_remark):
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


def kw_present(keywords: list[str], target: str):
    return any(kw in target for kw in keywords)


async def notify_users_and_unsubscribe(course: Course, msg: str, users: list[str]):
    """Notifies each user on Telegram and unsubscribes them from the course."""
    for uid in users:
        await BOT.send_message(
            chat_id=uid,
            text=msg,
            write_timeout=TIMEOUT_SECONDS,
        )
        DB.unsubscribe(course.get_course_name(), uid)


async def notify_admin(msg: str):
    """Sends a notification to Telegram feedback channel."""
    await BOT.send_message(FEEDBACK_CHANNEL_ID, msg, write_timeout=TIMEOUT_SECONDS)


def driver_alive():
    """Checks if the driver is still alive."""
    if DRIVER is None:
        return False
    try:
        if not DRIVER.service.is_connectable():
            return False
        DRIVER.service.assert_process_still_running()
        return True
    except WebDriverException:
        return False


def init(context: ContextTypes.DEFAULT_TYPE, db: Database, env: str):
    global BOT, DB, DRIVER, WAIT
    BOT = context.bot
    DB = db
    if not driver_alive():
        DRIVER, WAIT = init_driver(env)


def init_driver(env: str, wait_timeout=30):
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if env == PROD:
        options.binary_location = os.getenv("GOOGLE_CHROME_BIN")
        options.add_argument("--start-maximized")
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=Service(
            executable_path=(
                os.getenv("CHROMEDRIVER_PATH")
                if env == PROD
                else ChromeDriverManager().install()
            )
        ),
        options=options,
    )
    wait = WebDriverWait(driver, timeout=wait_timeout)
    return driver, wait


async def run(context: ContextTypes.DEFAULT_TYPE):
    """Runs the finder every minute."""
    global timeout

    if (now := pendulum.now()).minute % 30 == 0:
        print("Finder started at", now.to_rss_string())

    data = context.job.data
    init(context, data["db"], data["env"])

    try:
        await search_courses()
    except TimeoutException:
        if timeout is None:
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
