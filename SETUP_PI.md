# Raspberry Pi Setup Guide

## Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.9+ (should be pre-installed on recent Raspbian)
python3 --version

# Install pip
sudo apt install python3-pip python3-venv -y
```

## Installation

```bash
# Clone repository
git clone https://github.com/ryandeering/league-of-ireland-matchbot.git
cd league-of-ireland-matchbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create `matchbot_config.py` with your Reddit credentials:

```python
class MatchbotConfig:
    def __init__(self):
        self.base_url = "https://www.fotmob.com/api"
        self.headers = {"User-Agent": "Mozilla/5.0"}

        # Reddit credentials
        self.bot_username = "YOUR_BOT_USERNAME"
        self.bot_password = "YOUR_BOT_PASSWORD"
        self.client_id = "YOUR_CLIENT_ID"
        self.client_secret = "YOUR_CLIENT_SECRET"
        self.user_agent = "linux:leagueofirelandbot:v1.0 (by /u/YOUR_USERNAME)"
        self.subreddit = "LeagueOfIreland"
```

## Scheduling with Cron

> **Important:** When editing crontab, ADD these entries to your existing rules - do not replace the entire file. Any existing cron jobs will be preserved as long as you append rather than overwrite.

```bash
# View existing cron rules first
crontab -l

# Edit crontab (append new entries, don't erase existing ones)
crontab -e

# Add these entries:
```

```cron
# Post Premier Division thread every Friday at 12:00
0 12 * * 5 cd /home/pi/league-of-ireland-matchbot && /home/pi/league-of-ireland-matchbot/venv/bin/python premier_division.py >> /home/pi/logs/premier.log 2>&1

# Post First Division thread every Friday at 12:00
0 12 * * 5 cd /home/pi/league-of-ireland-matchbot && /home/pi/league-of-ireland-matchbot/venv/bin/python first_division.py >> /home/pi/logs/first.log 2>&1

# Run live updater every minute during match hours (Fri 18:00-23:00, Sat-Sun 12:00-23:00)
* 18-23 * * 5 cd /home/pi/league-of-ireland-matchbot && /home/pi/league-of-ireland-matchbot/venv/bin/python live_updater.py >> /home/pi/logs/live.log 2>&1
* 12-23 * * 6,0 cd /home/pi/league-of-ireland-matchbot && /home/pi/league-of-ireland-matchbot/venv/bin/python live_updater.py >> /home/pi/logs/live.log 2>&1
```

```bash
# Create logs directory
mkdir -p /home/pi/logs
```

## Alternative: Systemd Service

Create `/etc/systemd/system/matchbot-live.service`:

```ini
[Unit]
Description=LOI Matchbot Live Updater
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/league-of-ireland-matchbot
ExecStart=/home/pi/league-of-ireland-matchbot/venv/bin/python live_updater.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/matchbot-live.timer`:

```ini
[Unit]
Description=Run LOI Live Updater every minute

[Timer]
OnCalendar=*:*:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable matchbot-live.timer
sudo systemctl start matchbot-live.timer

# Check status
sudo systemctl status matchbot-live.timer
```

## Manual Testing

```bash
# Activate virtual environment
source venv/bin/activate

# Test API connection
python scripts/test_live_api.py

# Test post formatting (posts to r/test)
python scripts/test_post_live.py

# Run unit tests
python -m unittest discover -s tests
```

## File Overview

| File | Purpose | Schedule |
|------|---------|----------|
| `premier_division.py` | Posts weekly Premier thread | Friday 12:00 |
| `first_division.py` | Posts weekly First Division thread | Friday 12:00 |
| `fai_cup.py` | Posts FAI Cup thread | Match day |
| `live_updater.py` | Updates scores in real-time | Every minute during matches |

## Updating

```bash
cd /home/pi/league-of-ireland-matchbot
source venv/bin/activate

# Pull latest code
git pull origin main

# Update Python packages
pip install --upgrade pip
pip install -r requirements.txt --upgrade

# Verify everything works
python -m unittest discover -s tests
```

## Logs

```bash
# View recent logs
tail -f /home/pi/logs/live.log

# Check for errors
grep -i error /home/pi/logs/*.log

# Rotate logs (add to crontab for weekly rotation)
# 0 0 * * 1 find /home/pi/logs -name "*.log" -mtime +7 -delete
```
