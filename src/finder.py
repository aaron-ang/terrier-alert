# Standard library imports
import os
import sys
import time
from typing import Optional, Tuple

# Third-party imports
import pendulum
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import WebDriverException, TimeoutException
from telegram import constants, CallbackQuery
from telegram.ext import ContextTypes
from webdriver_manager.chrome import ChromeDriverManager

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import *
from utils.course import Course
from utils.db import Database

# Constants
load_dotenv()
FEEDBACK_CHANNEL_ID = str(os.getenv("FEEDBACK_CHANNEL_ID"))
REG_SCREENS = {
    "title": "Add Classes - Display",
    "options": "Registration Options",
    "confirmation": "Add Classes - Confirmation",
}

# Global variables
DB: Optional[Database] = None
DRIVER: Optional[webdriver.Chrome] = None
WAIT: Optional[WebDriverWait] = None
BOT = None
timeout: Optional[pendulum.DateTime] = None


def setup_chrome_options(env: str) -> webdriver.ChromeOptions:
    """Configure Chrome options based on environment."""
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if env == Environment.PROD:
        options.binary_location = os.getenv("GOOGLE_CHROME_BIN")
        options.add_argument("--start-maximized")
        options.add_argument("--headless=new")

    return options


def init_driver(
    env: str, wait_timeout: int = 30
) -> Tuple[webdriver.Chrome, WebDriverWait]:
    """Initialize Chrome driver with appropriate configuration."""
    options = setup_chrome_options(env)
    chrome_path = (
        os.getenv("CHROMEDRIVER_PATH")
        if env == Environment.PROD
        else ChromeDriverManager().install()
    )

    driver = webdriver.Chrome(
        service=Service(executable_path=chrome_path), options=options
    )
    wait = WebDriverWait(driver, timeout=wait_timeout)
    return driver, wait


def driver_alive() -> bool:
    """Check if the WebDriver is still operational."""
    if DRIVER is None:
        return False
    try:
        return (
            DRIVER.service.is_connectable()
            and DRIVER.service.assert_process_still_running() is None
        )
    except WebDriverException:
        return False


async def register_course(env: str, user_cache: dict, query: CallbackQuery):
    """Regiser a course for the user, to be called by `bot.py`"""
    # Create one driver per task
    driver, wait = init_driver(env, wait_timeout=10)
    course_name = user_cache.get(Message.LAST_SUBSCRIPTION, "")
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
    username, password = user_cache.get(Message.USERNAME, ""), user_cache.get(
        Message.PASSWORD, ""
    )
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
    wait.until(EC.title_is(REG_SCREENS["title"]))
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
    wait.until(EC.title_is(REG_SCREENS["options"]))
    driver.get(course.reg_url)
    wait.until(EC.title_is(REG_SCREENS["title"]))

    # Register
    input = driver.find_element(By.XPATH, input_xpath)
    add_class_btn = driver.find_element(
        By.XPATH, "/html/body/form/center[2]/table/tbody/tr/td[1]/input"
    )
    input.click()
    add_class_btn.click()

    alert: Alert = wait.until(EC.alert_is_present())
    alert.accept()

    wait.until(EC.title_is(REG_SCREENS["confirmation"]))
    cfm_img = driver.find_element(By.XPATH, "/html/body/table[4]/tbody/tr[2]/td[1]/img")
    if "checkmark" in cfm_img.get_attribute("src"):
        await query.edit_message_text(f"Successfully registered for {course_name}!")
    else:
        await query.edit_message_text(
            f"Failed to register for {course_name}\. Register manually [here]({course.reg_option_url})\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )
    driver.quit()


async def search_courses() -> None:
    """Process all course subscriptions."""
    for course_doc in DB.get_all_courses():
        course = Course(course_doc["name"])
        users = list(course_doc["users"])

        if not users:
            DB.remove_course(course.get_course_name())
            continue

        if course_doc["semester"] != Course.get_sem_year():
            await handle_expired_semester(course, course_doc["semester"], users)
            continue

        await process_course(course, users)


async def handle_expired_semester(
    course: Course, semester: str, users: list[str]
) -> None:
    """Handle courses from expired semesters."""
    msg = (
        f"You have been unsubscribed from {course} "
        f"since the deadline to add courses for {semester} has passed."
    )
    await notify_users_and_unsubscribe(course, msg, users)


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
    elif check_course_status(result_xpath, course_name_db):
        msg = f"{course_name_db} is now available! Use /register to add it to your schedule."
        await notify_users_and_unsubscribe(course, msg, users)


def check_course_status(result_xpath: str, course_name: str) -> bool:
    """Check if a course is available for registration."""
    keywords = ["Class Closed", "WebReg Restricted"]

    # Check main course section
    if not check_section_status(result_xpath, keywords):
        return False

    # Check discussion section if exists
    next_course_xpath = get_next_course_xpath(result_xpath)
    if is_related_section(next_course_xpath, course_name):
        if not check_section_status(next_course_xpath, keywords):
            return False

    return is_course_available(result_xpath)


def check_section_status(xpath: str, keywords: list[str]) -> bool:
    """Check if a course section has any restrictions."""
    remark = DRIVER.find_element(By.XPATH, f"{xpath}/td[13]/font").text
    return not any(kw in remark for kw in keywords)


def is_related_section(xpath: str, course_name: str) -> bool:
    """Check if the next section belongs to the same course."""
    next_course = DRIVER.find_element(By.XPATH, f"{xpath}/td[2]/font/a").text
    return next_course.split()[0] == course_name.split()[0]


def is_course_available(xpath: str) -> bool:
    """Check if a course has available seats."""
    remark = DRIVER.find_element(By.XPATH, f"{xpath}/td[13]/font").text
    seats = int(DRIVER.find_element(By.XPATH, f"{xpath}/td[7]/font").text)
    return not "Class Full" in remark and seats > 0


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
            write_timeout=TimeConstants.TIMEOUT_SECONDS,
        )
        DB.unsubscribe(course.get_course_name(), uid)


async def notify_admin(msg: str):
    """Sends a notification to Telegram feedback channel."""
    await BOT.send_message(
        FEEDBACK_CHANNEL_ID, msg, write_timeout=TimeConstants.TIMEOUT_SECONDS
    )


def driver_alive() -> bool:
    """Check if the WebDriver is still operational."""
    if DRIVER is None:
        return False
    try:
        return (
            DRIVER.service.is_connectable()
            and DRIVER.service.assert_process_still_running() is None
        )
    except WebDriverException:
        return False


def init(context: ContextTypes.DEFAULT_TYPE):
    global BOT, DB, DRIVER, WAIT
    BOT = context.bot
    DB = context.job.data["db"]
    if not driver_alive():
        DRIVER, WAIT = init_driver(DB.env)


async def run(context: ContextTypes.DEFAULT_TYPE):
    """Runs the finder every minute."""
    global timeout

    if (now := pendulum.now()).minute % 30 == 0:
        print("Finder started at", now.to_rss_string())

    init(context)

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
