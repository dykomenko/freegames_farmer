#!/usr/bin/env python3
"""Free Games Farmer — автоматический сбор бесплатных Steam-игр через ASF IPC."""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path

import aiohttp

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
CLAIMED_PATH = SCRIPT_DIR / "claimed.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("farmer")

# Reddit JSON API user-agent (required to avoid 429)
REDDIT_HEADERS = {
    "User-Agent": "freegames_farmer/1.0 (ASF auto-claimer)"
}

# Patterns to extract Steam IDs from URLs and text
RE_STEAM_APP = re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE)
RE_STEAM_SUB = re.compile(r"store\.steampowered\.com/sub/(\d+)", re.IGNORECASE)
RE_EXPLICIT_APP = re.compile(r"\bapp/(\d+)\b")
RE_EXPLICIT_SUB = re.compile(r"\bsub/(\d+)\b")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error("config.json not found at %s", CONFIG_PATH)
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_claimed() -> set[str]:
    if not CLAIMED_PATH.exists():
        return set()
    with open(CLAIMED_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def save_claimed(claimed: set[str]) -> None:
    with open(CLAIMED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(claimed), f, indent=2)


def extract_ids(text: str) -> list[tuple[str, str]]:
    """Extract (type, id) pairs from text. type is 'app' or 'sub'."""
    ids = []
    seen = set()

    for pattern, kind in [
        (RE_STEAM_SUB, "sub"),
        (RE_STEAM_APP, "app"),
        (RE_EXPLICIT_SUB, "sub"),
        (RE_EXPLICIT_APP, "app"),
    ]:
        for match in pattern.finditer(text):
            key = f"{kind}/{match.group(1)}"
            if key not in seen:
                seen.add(key)
                ids.append((kind, match.group(1)))

    return ids


async def fetch_reddit(session: aiohttp.ClientSession, subreddit: str, limit: int) -> list[dict]:
    """Fetch recent posts from a subreddit via JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        async with session.get(url, headers=REDDIT_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                log.warning("Reddit r/%s returned %d", subreddit, resp.status)
                return []
            data = await resp.json()
            return [child["data"] for child in data.get("data", {}).get("children", [])]
    except Exception as e:
        log.error("Failed to fetch r/%s: %s", subreddit, e)
        return []


async def asf_add_license(
    session: aiohttp.ClientSession,
    asf_url: str,
    password: str,
    bot_name: str,
    license_type: str,
    license_id: str,
) -> dict:
    """Send addlicense command to ASF via IPC."""
    url = f"{asf_url.rstrip('/')}/Api/Command"
    headers = {"Content-Type": "application/json"}
    if password:
        headers["Authentication"] = password

    command = f"addlicense {bot_name} {license_type}/{license_id}"
    payload = {"Command": command}

    try:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            result = await resp.json()
            return {
                "success": result.get("Success", False),
                "message": result.get("Message", ""),
                "result": result.get("Result", ""),
                "command": command,
            }
    except Exception as e:
        return {"success": False, "message": str(e), "result": "", "command": command}


async def main():
    config = load_config()
    asf_url = config.get("asf_url", "http://localhost:1242")
    asf_password = config.get("asf_password", "")
    bot_name = config.get("bot_name", "ASF")
    subreddits = config.get("subreddits", ["FreeGamesOnSteam"])
    check_limit = config.get("check_limit", 50)

    claimed = load_claimed()
    new_claims = []

    async with aiohttp.ClientSession() as session:
        # Fetch posts from all subreddits
        all_posts = []
        for sub in subreddits:
            posts = await fetch_reddit(session, sub, check_limit)
            log.info("r/%s: fetched %d posts", sub, len(posts))
            all_posts.extend(posts)

        # Extract IDs from posts
        to_claim = []
        for post in all_posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')} {post.get('url', '')}"
            ids = extract_ids(text)
            for kind, steam_id in ids:
                key = f"{kind}/{steam_id}"
                if key not in claimed:
                    to_claim.append((kind, steam_id, post.get("title", "?")))

        if not to_claim:
            log.info("No new games to claim")
            return

        log.info("Found %d new license(s) to claim", len(to_claim))

        # Send to ASF
        for kind, steam_id, title in to_claim:
            key = f"{kind}/{steam_id}"
            result = await asf_add_license(session, asf_url, asf_password, bot_name, kind, steam_id)

            if result["success"]:
                log.info("OK: %s — %s | %s", key, title, result["result"])
            else:
                log.warning("FAIL: %s — %s | %s", key, title, result["message"])

            claimed.add(key)
            new_claims.append({"key": key, "title": title, "result": result})

    save_claimed(claimed)
    log.info("Done. Processed %d license(s), total claimed: %d", len(new_claims), len(claimed))


if __name__ == "__main__":
    asyncio.run(main())
