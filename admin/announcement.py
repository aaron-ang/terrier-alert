"""One-time script to send out announcements to users"""

import os
import sys
import asyncio
from datetime import datetime
import telegram
from telegram import Message
from dotenv import load_dotenv

sys.path.append("./")
from utils.db import Database
from utils.constants import Environment, TimeConstants


async def send_maintenance_announcement():
    """Send maintenance message to all users"""
    announcement = "Terrier Alert has resumed service. Thank you for your patience!"
    await broadcast_message(announcement)


async def send_live_announcement():
    """Send announcement to all users when service goes back live"""
    announcement = (
        "Terrier Alert will be unavailable until further notice as we are upgrading our systems to "
        "integrate with the new course search. If you are interested in contributing or maintaining the project, "
        "please use the /feedback command to get in touch with us (and specify your Telegram username). "
        "Thank you for your patience!"
    )
    # announcement = (
    #     "Thank you for using Terrier Alert!\n"
    #     f"*Release Notes ({datetime.now().strftime('%B %-d, %Y')})*\n"
    #     # "*What's 🆕*\n"
    #     # "• 🚀 /resubscribe: Received a notification but failed to secure your spot? "
    #     # "Use this command to quickly subscribe to the same class!\n"
    #     # "• 🔍 Scraping logic: In light of classes that may reopen, "
    #     # "Terrier Alert will ignore Closed/Restricted classes (instead of sending a notification) "
    #     # "but will continue to monitor them for openings\n"
    #     # "• 🏫 Added *CGS, SPH, SED* to the list of schools\n"
    #     "*Bug Fixes*\n"
    #     "• 🔧 Fixed: Some users were not able to subscribe to classes. "
    #     "We have since resolved this issue and added additional error handling for more visibility in the future. "
    #     "Apologies for any inconvenience caused!\n"
    # )
    await broadcast_message(announcement)


async def broadcast_message(message):
    """Send message to all users"""
    for user in DB.get_all_users():
        try:
            msg: Message = await BOT.send_message(
                user["user"],
                message,
                parse_mode="Markdown",
                write_timeout=TimeConstants.TIMEOUT_SECONDS,
            )
            await msg.pin()
        except Exception as e:
            print(f"Error sending message to {user['user']}: {e}")


async def main(env: Environment):
    global BOT, DB
    load_dotenv()
    bot_token = os.getenv(
        "TELEGRAM_TOKEN" if env == Environment.PROD else "TEST_TELEGRAM_TOKEN"
    )
    BOT = telegram.Bot(bot_token)
    DB = Database(env)
    await send_live_announcement()


if __name__ == "__main__":
    try:
        asyncio.run(main(Environment.PROD))
    except Exception as e:
        print(e)
    else:
        print("Announcement sent successfully.")
