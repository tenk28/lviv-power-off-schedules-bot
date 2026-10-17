# Energy Schedule Telegram Bot

This project polls the Lviv power company (LOE) schedule API and sends the outage schedule image to a Telegram chat when the schedule changes.  
It runs continuously in Docker and starts automatically after a reboot.

---

## Requirements

- Docker with the Compose plugin
- Telegram bot token and chat ID

Works on amd64 and arm64 (e.g. Raspberry Pi).

Make sure Docker starts on boot (needed once per device):
```bash
sudo systemctl enable --now docker
```

---

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/tenk28/lviv-power-off-schedules-bot.git
cd lviv-power-off-schedules-bot
```

### 2. Configure .env
```bash
vim .env
```

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `CHAT_ID` | Chat to send schedules to |
| `CHECK_DELAY_SECS` | Delay between checks, in seconds |
| `GROUP` | Optional. Outage group to track, e.g. `3.1`. A message is sent only when this group's outage hours change (a new date with the same hours is not sent). Leave empty to track the whole schedule |
| `FAIL_ALERT_THRESHOLD` | Optional, default `3`. After this many failed checks in a row (API unavailable, format changed, group not found) the bot sends a warning to the chat, and a second message once it recovers |

### 3. Build and start
```bash
docker compose up -d --build
```

The container uses `restart: unless-stopped`: it restarts after a crash and after a device reboot, unless you stopped it yourself.  
The last seen schedule is stored in `./data/data.txt`.

---

## Usage

### Check status
```bash
docker compose ps
```

### View logs
```bash
docker compose logs -f
```

### Restart
```bash
docker compose restart
```

### Apply changes (after `git pull` or editing `.env`)
```bash
docker compose up -d --build
```

### Stop
```bash
docker compose stop
```

`stop` keeps the container, and it won't start again after a reboot until you run `docker compose up -d`.  
`docker compose down` removes the container completely.

### Resend the current schedule
Delete the saved state and restart:
```bash
sudo rm data/data.txt
```
```bash
docker compose restart
```
