#!/usr/bin/env python3

import requests
import os
import re
import html
import asyncio
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder
from typing import NamedTuple

load_dotenv()  # loads .env from current folder

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = int(os.getenv('CHAT_ID'))
CHECK_DELAY_SECS = int(os.getenv('CHECK_DELAY_SECS')) # seconds
API_BASE_URL = "https://api.loe.lviv.ua"
SCHEDULE_API_URL = f"{API_BASE_URL}/api/menus?page=1&type=photo-grafic"
DATA_FILEPATH = os.getenv('DATA_FILEPATH', "data.txt")
GROUP = os.getenv('GROUP', "").strip() # e.g. "3.1"; empty means track the whole schedule

class PowerOffData(NamedTuple):
    power_off_str: str
    picture_url: str

def html_to_text(raw_html: str) -> str:
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', raw_html, flags=re.S)
    lines = [html.unescape(re.sub(r'<[^>]+>', '', p)).strip() for p in paragraphs]
    return "\n".join(line for line in lines if line)

def build_message(power_off_str: str) -> tuple[str, str]:
    """Returns (text to track for changes, caption to send)."""
    if not GROUP:
        return power_off_str, power_off_str

    lines = power_off_str.splitlines()
    updated_at = next((l for l in lines if l.startswith("Інформація станом")), "")
    group_line = next((l for l in lines if l.startswith(f"Група {GROUP}.")), f"Група {GROUP}. Немає даних.")

    # Only the group line is tracked, so a new date or a refresh
    # of other groups doesn't trigger a message
    tracked = group_line
    caption = "\n".join(l for l in (updated_at, group_line) if l)
    return tracked, caption

def get_poweroff_data() -> PowerOffData | None:
    response = requests.get(SCHEDULE_API_URL, timeout=10)
    response.raise_for_status()

    # The API answers either with a plain list or with a JSON-LD (hydra) object
    payload = response.json()
    members = payload.get("hydra:member", []) if isinstance(payload, dict) else payload
    if not members:
        return None

    # The site shows menuItems[0] as today's schedule
    menu_items = members[0].get("menuItems", [])
    if not menu_items:
        return None

    today = menu_items[0]
    poweroff_text = html_to_text(today.get("rawHtml") or "")
    image_path = today.get("imageUrl") or ""

    if not poweroff_text or not image_path:
        return None

    return PowerOffData(
        poweroff_text,
        API_BASE_URL + image_path,
    )

def download_picture_to_memory(pic_url: str) -> bytes:
    response = requests.get(pic_url, timeout=10)
    response.raise_for_status()

    return response.content

async def check_for_update(app):
    power_off_data = await asyncio.to_thread(get_poweroff_data)
    if not power_off_data:
        print("Schedule not found in API response")
        return

    prev_data_str: str = ""

    if os.path.isfile(DATA_FILEPATH):
        with open(DATA_FILEPATH, "r") as f:
            prev_data_str = f.read()

    tracked_str, caption = build_message(power_off_data.power_off_str)
    if prev_data_str == tracked_str:
        print("Schedule hasn't updated")
        return

    print("New schedule detected, updating")

    new_pic_bytes = await asyncio.to_thread(download_picture_to_memory, power_off_data.picture_url)
    await app.bot.send_photo(chat_id=CHAT_ID, photo=new_pic_bytes, caption=caption, disable_notification=True)

    with open(DATA_FILEPATH, "w") as f:
        f.write(tracked_str)

async def polling(app):
    while(True):
        print('New verification iteration')
        try:
            await check_for_update(app)
        except Exception as e:
            print(f"Verification failed: {e!r}")

        await asyncio.sleep(CHECK_DELAY_SECS)

async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    print("Bot started")
    await polling(app)

if __name__ == '__main__':
    asyncio.run(main())
