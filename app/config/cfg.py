import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

API_ID = os.getenv("APP_ID")
API_HASH = os.getenv("APP_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
