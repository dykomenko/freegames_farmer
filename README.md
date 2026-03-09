# freegames_farmer

Automatically claims free Steam games via [ArchiSteamFarm](https://github.com/JustArchiNET/ArchiSteamFarm) IPC API.

## How it works

```
u/ASFinfo (primary)          r/FreeGamesOnSteam (fallback)
  │  curated !addlicense       │  Steam store URLs
  │  commands with correct     │
  │  subIDs (s/) and appIDs    │
  ▼  (a/)                      ▼
  ┌────────────────────────────────┐
  │  Parse & deduplicate IDs       │
  └───────────────┬────────────────┘
                  ▼
  ASF IPC API → addlicense ASF s/XXXXX
                  │
                  ▼
         claimed.json (dedup)
```

**Primary source** — [u/ASFinfo](https://reddit.com/user/ASFinfo): a Reddit bot that posts ready-made `!addlicense` commands with correct `s/subID` for free promotional packages.

**Fallback** — [r/FreeGamesOnSteam](https://reddit.com/r/FreeGamesOnSteam): extracts `a/appID` from Steam store URLs.

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
| `subreddits` | Fallback subreddits to parse for Steam URLs |
| `check_limit` | Number of recent posts to fetch per source |

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
# edit config.json with your ASF IPC password
python3 farmer.py
```
