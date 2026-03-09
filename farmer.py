#!/usr/bin/env python3
"""Free Games Farmer — автоматический сбор бесплатных Steam-игр через ASF IPC.

Primary source: u/ASFinfo on Reddit — a bot that posts ready-made
!addlicense commands with correct subIDs for free promotional packages.
"""

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

REDDIT_HEADERS = {
    "User-Agent": "freegames_farmer/1.0 (ASF auto-claimer)"
}

# Pattern to extract !addlicense commands from u/ASFinfo posts
# Matches: !addlicense asf a/12345  or  !addlicense asf s/12345
RE_ADDLICENSE = re.compile(r"!addlicense\s+\w+\s+([as])/(\d+)", re.IGNORECASE)

# Fallback patterns for store URLs (used for r/FreeGamesOnSteam posts)
RE_STEAM_APP = re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE)
RE_STEAM_SUB = re.compile(r"store\.steampowered\.com/sub/(\d+)", re.IGNORECASE)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error("config.json not found at %s", CONFIG_PATH)
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_claimed() -> set[str]:
    if not CLAIMED_PATH.exists():
        return set()
    try:
        text = CLAIMED_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return set()
        return set(json.loads(text))
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("claimed.json is corrupted (%s), starting fresh", e)
        return set()


def save_claimed(claimed: set[str]) -> None:
    with open(CLAIMED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(claimed), f, indent=2)


# Map short prefix to ASF command prefix
PREFIX_MAP = {"a": "a", "s": "s", "app": "a", "sub": "s"}


def extract_ids_from_addlicense(text: str) -> list[tuple[str, str]]:
    """Extract (prefix, id) from !addlicense commands. prefix is 'a' or 's'."""
    ids = []
    seen = set()
    for match in RE_ADDLICENSE.finditer(text):
        prefix = match.group(1).lower()  # 'a' or 's'
        steam_id = match.group(2)
        key = f"{prefix}/{steam_id}"
        if key not in seen:
            seen.add(key)
            ids.append((prefix, steam_id))
    return ids


def extract_ids_from_urls(text: str) -> list[tuple[str, str]]:
    """Fallback: extract IDs from Steam store URLs."""
    ids = []
    seen = set()
    for pattern, prefix in [(RE_STEAM_SUB, "s"), (RE_STEAM_APP, "a")]:
        for match in pattern.finditer(text):
            steam_id = match.group(1)
            key = f"{prefix}/{steam_id}"
            if key not in seen:
                seen.add(key)
                ids.append((prefix, steam_id))
    return ids


async def fetch_reddit_user(session: aiohttp.ClientSession, username: str, limit: int) -> list[dict]:
    """Fetch recent posts/comments from a Reddit user."""
    url = f"https://www.reddit.com/user/{username}.json?sort=new&limit={limit}"
    try:
        async with session.get(url, headers=REDDIT_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                log.warning("Reddit u/%s returned %d", username, resp.status)
                return []
            text = await resp.text()
            if not text.strip():
                log.warning("Reddit u/%s returned empty body", username)
                return []
            data = json.loads(text)
            return [child["data"] for child in data.get("data", {}).get("children", [])]
    except Exception as e:
        log.error("Failed to fetch u/%s: %s", username, e)
        return []


async def fetch_reddit_sub(session: aiohttp.ClientSession, subreddit: str, limit: int) -> list[dict]:
    """Fetch recent posts from a subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        async with session.get(url, headers=REDDIT_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                log.warning("Reddit r/%s returned %d", subreddit, resp.status)
                return []
            text = await resp.text()
            if not text.strip():
                log.warning("Reddit r/%s returned empty body", subreddit)
                return []
            data = json.loads(text)
            return [child["data"] for child in data.get("data", {}).get("children", [])]
    except Exception as e:
        log.error("Failed to fetch r/%s: %s", subreddit, e)
        return []


async def asf_add_license(
    session: aiohttp.ClientSession,
    asf_url: str,
    password: str,
    bot_name: str,
    prefix: str,
    license_id: str,
) -> dict:
    """Send addlicense command to ASF via IPC. prefix is 'a' (app) or 's' (sub)."""
    url = f"{asf_url.rstrip('/')}/Api/Command"
    headers = {"Content-Type": "application/json"}
    if password:
        headers["Authentication"] = password

    command = f"addlicense {bot_name} {prefix}/{license_id}"
    payload = {"Command": command}

    try:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if not text.strip():
                return {"success": False, "message": "Empty ASF response", "result": "", "command": command}
            result = json.loads(text)
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
    to_claim: list[tuple[str, str, str]] = []  # (prefix, id, title)

    async with aiohttp.ClientSession() as session:

        # === Primary source: u/ASFinfo (curated addlicense commands) ===
        asfinfo_posts = await fetch_reddit_user(session, "ASFinfo", check_limit)
        log.info("u/ASFinfo: fetched %d entries", len(asfinfo_posts))

        for post in asfinfo_posts:
            body = post.get("body", post.get("selftext", ""))
            title = post.get("link_title", post.get("title", "?"))
            ids = extract_ids_from_addlicense(body)
            for prefix, steam_id in ids:
                key = f"{prefix}/{steam_id}"
                if key not in claimed:
                    to_claim.append((prefix, steam_id, title))

        # === Fallback: subreddits (Steam store URLs) ===
        for sub in subreddits:
            posts = await fetch_reddit_sub(session, sub, check_limit)
            log.info("r/%s: fetched %d posts", sub, len(posts))
            for post in posts:
                text = f"{post.get('title', '')} {post.get('selftext', '')} {post.get('url', '')}"
                ids = extract_ids_from_urls(text)
                for prefix, steam_id in ids:
                    key = f"{prefix}/{steam_id}"
                    if key not in claimed:
                        to_claim.append((prefix, steam_id, post.get("title", "?")))

        # Deduplicate
        seen = set()
        unique = []
        for prefix, steam_id, title in to_claim:
            key = f"{prefix}/{steam_id}"
            if key not in seen:
                seen.add(key)
                unique.append((prefix, steam_id, title))
        to_claim = unique

        if not to_claim:
            log.info("No new games to claim")
            return

        log.info("Found %d new license(s) to claim", len(to_claim))

        # === Send to ASF ===
        new_claims = []
        for prefix, steam_id, title in to_claim:
            key = f"{prefix}/{steam_id}"
            result = await asf_add_license(session, asf_url, asf_password, bot_name, prefix, steam_id)

            raw = result["result"]
            if isinstance(raw, dict):
                status = str(raw.get("Result", raw))[:120]
            elif isinstance(raw, str) and raw:
                status = raw.split("\n")[0][:120]
            else:
                status = result["message"]
            # Don't save rate-limited or connection-failed entries — retry next run
            retry = "RateLimitExceeded" in status or (not result["success"] and "401" not in status)
            if result["success"]:
                log.info("OK: %s — %s | %s", key, title, status)
            else:
                log.warning("FAIL: %s — %s | %s", key, title, status)

            if not retry:
                claimed.add(key)
            else:
                log.info("RETRY NEXT RUN: %s", key)
            new_claims.append(key)

    save_claimed(claimed)
    log.info("Done. Processed %d, total claimed: %d", len(new_claims), len(claimed))


if __name__ == "__main__":
    asyncio.run(main())
