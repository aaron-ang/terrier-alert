import os
import sys
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import finder
from src.finder import DEV

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    asyncio.run(finder.main(DEV))
