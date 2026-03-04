# freegames_farmer

Automatically claims free Steam games via [ArchiSteamFarm](https://github.com/JustArchiNET/ArchiSteamFarm) IPC API.

Parses [r/FreeGamesOnSteam](https://reddit.com/r/FreeGamesOnSteam) for new free games and sends `addlicense` commands to all ASF bots.

## How it works

```
Reddit (r/FreeGamesOnSteam)
       │  fetch new posts via JSON API
       ▼
  Parse appID / subID from Steam URLs
       │
       ▼
  ASF IPC API → addlicense ASF app/XXX
       │
       ▼
  Save claimed IDs to claimed.json (dedup)
```

## Requirements

- Python 3.10+
- ArchiSteamFarm with IPC enabled
- Linux with systemd (for auto-scheduling)

## Quick start

1. **Clone and install:**

```bash
git clone https://github.com/dykomenko/freegames_farmer.git
cd freegames_farmer
bash install.sh
```

2. **Configure** `~/freegames_farmer/config.json`:

```json
{
  "asf_url": "http://localhost:1242",
  "asf_password": "YOUR_ASF_IPC_PASSWORD",
  "bot_name": "ASF",
  "subreddits": ["FreeGamesOnSteam"],
  "check_limit": 50
}
```

| Field | Description |
|---|---|
| `asf_url` | ASF IPC endpoint |
| `asf_password` | IPC password from ASF.json (`IPCPassword`) |
| `bot_name` | `ASF` = all bots, or a specific bot name |
| `subreddits` | List of subreddits to parse |
| `check_limit` | Number of recent posts to fetch per subreddit |

3. **Test run:**

```bash
~/freegames_farmer/venv/bin/python3 ~/freegames_farmer/farmer.py
```

## Scheduling

`install.sh` sets up a **systemd user timer** that runs daily at 12:00.

```bash
# Check timer status
systemctl --user status freegames-farmer.timer

# View run logs
journalctl --user -u freegames-farmer.service

# Manual trigger
systemctl --user start freegames-farmer.service
```

## Manual install (without install.sh)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp config.json ~/freegames_farmer/config.json  # edit with your password
python3 farmer.py
```
