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
FAIL_ALERT_THRESHOLD = int(os.getenv('FAIL_ALERT_THRESHOLD', "3")) # consecutive failed checks before alerting

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
    group_line = next((l for l in lines if l.startswith(f"Група {GROUP}.")), None)
    if group_line is None:
        raise ValueError(f"Group {GROUP} not found in schedule")

    # Only the group line is tracked, so a new date or a refresh
    # of other groups doesn't trigger a message
    tracked = group_line
    caption = "\n".join(l for l in (updated_at, group_line) if l)
    return tracked, caption

def get_poweroff_data() -> PowerOffData:
    response = requests.get(SCHEDULE_API_URL, timeout=10)
    response.raise_for_status()

    # The API answers either with a plain list or with a JSON-LD (hydra) object
    payload = response.json()
    members = payload.get("hydra:member", []) if isinstance(payload, dict) else payload
    if not members:
        raise ValueError("No menus in API response")

    # The site shows menuItems[0] as today's schedule
    menu_items = members[0].get("menuItems", [])
    if not menu_items:
        raise ValueError("No menu items in API response")

    today = menu_items[0]
    poweroff_text = html_to_text(today.get("rawHtml") or "")
    image_path = today.get("imageUrl") or ""

    if not poweroff_text or not image_path:
        raise ValueError("Today's schedule text or image is empty")

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

async def send_alert(app, text: str):
    try:
        await app.bot.send_message(chat_id=CHAT_ID, text=text)
    except Exception as e:
        print(f"Failed to send alert: {e!r}")
        return False
    return True

async def polling(app):
    failures = 0
    alerted = False

    while(True):
        print('New verification iteration')
        try:
            await check_for_update(app)
        except Exception as e:
            failures += 1
            print(f"Verification failed ({failures} in a row): {e!r}")

            if failures >= FAIL_ALERT_THRESHOLD and not alerted:
                alerted = await send_alert(
                    app,
                    f"⚠️ Бот не може отримати графік відключень (невдалих перевірок поспіль: {failures}).\n"
                    f"Остання помилка: {e!r}",
                )
        else:
            if alerted:
                await send_alert(app, "✅ Бот знову отримує графік відключень.")
            failures = 0
            alerted = False

        await asyncio.sleep(CHECK_DELAY_SECS)

async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    print("Bot started")
    await polling(app)

if __name__ == '__main__':
    asyncio.run(main())
