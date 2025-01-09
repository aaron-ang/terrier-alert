"""Set bot commands and descriptions"""

import os
import asyncio
from telegram import Bot, BotCommand
from dotenv import load_dotenv

COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("subscribe", "Subscribe to a course"),
    # BotCommand("register", "Register for a subscribed course"),
    BotCommand("resubscribe", "Resubscribe to last subscribed course"),
    BotCommand("unsubscribe", "Unsubscribe from a course"),
    BotCommand("help", "Important information"),
    BotCommand("feedback", "Report bugs and submit feedback"),
    BotCommand("about", "Tech stack and source code"),
]


async def main():
    load_dotenv()
    BOT_TOKENS = [os.getenv("TELEGRAM_TOKEN"), os.getenv("TEST_TELEGRAM_TOKEN")]
    for BOT_TOKEN in BOT_TOKENS:
        bot = Bot(token=BOT_TOKEN)
        successs = await bot.set_my_commands(COMMANDS)
        if not successs:
            raise Exception(f"Failed to set commands in Bot: {BOT_TOKEN}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(e)
    else:
        print("Succesfully set bot commands.")
