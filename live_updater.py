"""
Live score updater for League of Ireland match threads
Polls API-Football with adaptive frequency and rate limiting
Updates Reddit posts with live scores and goal scorers
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Any
from tabulate import tabulate
import praw
import requests
from matchbot_config import MatchbotConfig
from common import (
    table_headers,
    match_table_headers,
    normalise_team_name,
    ordinal_suffix,
    get_last_matches,
    format_live_fixture,
    format_scorers_inline,
    load_cache,
)
from rate_limiter import APIRateLimiter, APIClient

# API Rate Limiting Configuration
API_DAILY_LIMIT = 100  # API-Football free tier: 100 requests/day
API_PER_MINUTE_LIMIT = 10  # Max requests per minute
API_MAX_RETRIES = 3  # Number of retry attempts on failure
CIRCUIT_BREAKER_THRESHOLD = 5  # Consecutive failures before circuit opens
CIRCUIT_BREAKER_RECOVERY_SECONDS = 300  # 5 minutes recovery time

# Caching Configuration
TABLE_CACHE_SECONDS = 1800  # Cache league tables for 30 minutes

# League IDs
LEAGUE_ID_PREMIER = 357
LEAGUE_ID_FIRST = 358
LEAGUE_ID_FAI_CUP = 359

logger = logging.getLogger(__name__)
config = MatchbotConfig()
rate_limiter = APIRateLimiter(
    daily_limit=API_DAILY_LIMIT,
    per_minute_limit=API_PER_MINUTE_LIMIT,
    max_retries=API_MAX_RETRIES,
    circuit_breaker_threshold=CIRCUIT_BREAKER_THRESHOLD,
    circuit_breaker_recovery_time=CIRCUIT_BREAKER_RECOVERY_SECONDS,
)

# Global cache for league tables
_table_cache: Dict[int, Dict[str, Any]] = {}


def get_live_fixtures(league_ids, api_client=None):
    """
    Fetch live fixtures for multiple leagues in a single API call.

    Args:
        league_ids: list of league IDs to fetch (e.g., [357, 358, 359])
        api_client: Optional APIClient instance. If None, uses direct requests.

    Returns:
        List of fixture dictionaries or empty list on failure
    """
    league_ids_str = "-".join(str(lid) for lid in league_ids)

    if api_client:
        try:
            response = api_client.call_with_retry(
                "/fixtures",
                params={"live": league_ids_str},
                timeout=10,
            )
            return response.get("response", [])
        except requests.exceptions.RequestException as e:
            logger.error("Error fetching live fixtures: %s", e)
            return []

    # Fallback to direct requests if no api_client provided
    try:
        response = requests.get(
            f"{config.base_url}/fixtures",
            params={"live": league_ids_str},
            headers=config.headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["response"]
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching live fixtures: %s", e)
        return []


def get_league_table(league_id: int) -> List[Dict[str, Any]]:
    """Return league table for a specific league with caching.

    Tables are cached for 30 minutes as they only change after matches finish.
    This reduces API calls from ~6/hour to ~2/hour during match days.

    Args:
        league_id: League ID (357=Premier, 358=First, 359=FAI Cup)

    Returns:
        List of team standings dictionaries
    """
    now = time.time()

    # Check if we have a valid cached table
    if league_id in _table_cache:
        cache_entry = _table_cache[league_id]
        if now < cache_entry["expires"]:
            logger.debug(
                "Using cached table for league %s (expires in %ds)",
                league_id,
                int(cache_entry["expires"] - now)
            )
            return cache_entry["data"]

    # Cache miss or expired - fetch fresh data
    try:
        response = requests.get(
            f"{config.base_url}/standings",
            headers=config.headers,
            params={
                "league": league_id,
                "season": datetime.now().year,
            },
            timeout=5,
        )
        response.raise_for_status()
        table_data = response.json()["response"][0]["league"]["standings"][0]

        # Update cache
        _table_cache[league_id] = {
            "data": table_data,
            "expires": now + TABLE_CACHE_SECONDS,
        }
        logger.info("Fetched and cached table for league %s", league_id)
        return table_data

    except requests.exceptions.RequestException as e:
        logger.error("Error getting league table for %s: %s", league_id, e)

        # Return stale cache if available, otherwise empty
        if league_id in _table_cache:
            logger.warning("Using stale cache for league %s", league_id)
            return _table_cache[league_id]["data"]
        return []


def _format_match_date_section(date_str, matches_list):
    """Format matches for a single date into a markdown section."""
    date_extracted = datetime.strptime(date_str, "%Y-%m-%d")
    date_header = date_extracted.strftime(
        f"%A, %B {ordinal_suffix(date_extracted.day)}"
    )
    section_header = f"## {date_header}\n\n"

    matches = [format_live_fixture(match) for match in matches_list]
    match_table = tabulate(
        matches, headers=match_table_headers, tablefmt='pipe'
    )

    section = f"{section_header}{match_table}\n"
    for match in matches_list:
        scorers = format_scorers_inline(match)
        if scorers:
            section += f"\n{scorers}\n"
    section += "\n"

    return section


def build_premier_body(matches_data, league_table, gameweek_number):
    """Build the body text for Premier Division post."""
    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores will be updated during matches*\n\n"

    for date, matches_list in sorted(matches_by_date.items()):
        body += _format_match_date_section(date, matches_list)

    table_data = [
        [
            item["rank"],
            normalise_team_name(item["team"]["name"]),
            item["all"]["played"],
            item["all"]["win"],
            item["all"]["draw"],
            item["all"]["lose"],
            item["all"]["goals"]["for"],
            item["all"]["goals"]["against"],
            item["goalsDiff"],
            item["points"],
            get_last_matches(item["team"]["id"], league_table),
        ]
        for item in league_table
    ]

    if gameweek_number - 1 > 0:
        body += f"## League Table, as of Round {gameweek_number - 1}\n\n"
        standings_table = tabulate(
            table_data, headers=table_headers, tablefmt='pipe'
        )
        body += f"{standings_table}\n\n"

    body += (
        "\n\n Welcome to the discussion thread for the League of Ireland"
        " Premier Division. Remember to follow the subreddit rules and be"
        " civil to each other. Enjoy the game. \n\n"
    )
    body += (
        "\n\n This post was created by a bot. If you have any feedback or"
        " suggestions, please message /u/LOIMatchThreads."
    )

    return body


def build_first_body(matches_data, league_table, gameweek_number):
    """Build the body text for First Division post."""
    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores will be updated during matches*\n\n"

    for date, matches_list in sorted(matches_by_date.items()):
        body += _format_match_date_section(date, matches_list)

    table_data = [
        [
            item["rank"],
            normalise_team_name(item["team"]["name"]),
            item["all"]["played"],
            item["all"]["win"],
            item["all"]["draw"],
            item["all"]["lose"],
            item["all"]["goals"]["for"],
            item["all"]["goals"]["against"],
            item["goalsDiff"],
            item["points"],
            get_last_matches(item["team"]["id"], league_table),
        ]
        for item in league_table
    ]

    if gameweek_number - 1 > 0:
        body += f"## League Table, as of Round {gameweek_number - 1}\n\n"
        standings_table = tabulate(
            table_data, headers=table_headers, tablefmt='pipe'
        )
        body += f"{standings_table}\n\n"

    body += (
        "\n\n Welcome to the discussion thread for the League of Ireland"
        " First Division. Remember to follow the subreddit rules and be"
        " civil to each other. Enjoy the game. \n\n"
    )
    body += (
        "\n\n This post was created by a bot. If you have any feedback or"
        " suggestions, please message /u/LOIMatchThreads."
    )

    return body


def build_cup_body(matches_data, current_round):
    """Build the body text for FAI Cup post."""
    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = (
        f"*Live scores will be updated during matches*\n\n"
        f"## {current_round}\n\n"
    )

    for date, matches_list in sorted(matches_by_date.items()):
        date_extracted = datetime.strptime(date, "%Y-%m-%d")
        date_header = date_extracted.strftime(f"%A, %B {date_extracted.day}")
        section_header = f"### {date_header}\n\n"

        matches = [format_live_fixture(match) for match in matches_list]

        match_table = tabulate(
            matches, headers=match_table_headers, tablefmt='pipe'
        )
        body += f"{section_header}{match_table}\n"

        # Add scorers inline under table
        for match in matches_list:
            scorers = format_scorers_inline(match)
            if scorers:
                body += f"\n{scorers}\n"
        body += "\n"

    body += (
        "\n\n Welcome to the discussion thread for the Sports Direct "
        "FAI Cup. Remember to follow the subreddit rules and be civil "
        "to each other. Enjoy the game. \n\n"
    )

    body += (
        "\n\n This post was created by a bot. If you have any feedback or "
        "suggestions, please message /u/LOIMatchThreads."
    )

    return body


def update_reddit_post(post_id: str, new_body: str) -> bool:
    """Edit an existing Reddit post with updated body.

    Args:
        post_id: Reddit post ID
        new_body: New markdown body text

    Returns:
        True if successful, False otherwise
    """
    try:
        reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.bot_username,
            password=config.bot_password,
            user_agent=config.user_agent,
        )

        post = reddit.submission(id=post_id)
        post.edit(new_body)
        logger.info("Updated post %s", post_id)
        return True
    except (
            praw.exceptions.PRAWException,
            requests.exceptions.RequestException
    ) as e:
        logger.error("Error updating post %s: %s", post_id, e)
        return False


def update_league_thread(
        competition_name: str,
        cache_data: Dict[str, Any],
        fixtures: List[Dict[str, Any]],
        league_id: int,
) -> None:
    """Update a league thread with live scores and standings.

    Args:
        competition_name: Name of competition ("premier_division", etc.)
        cache_data: Cached data for this competition
        fixtures: List of fixtures for this league
        league_id: League ID (357, 358, or 359)
    """
    comp_display = competition_name.replace('_', ' ').title()
    logger.info("Updating %s thread...", comp_display)

    post_id = cache_data["post_id"]
    current_round = cache_data["round"]
    league_table = get_league_table(league_id)

    # Build appropriate body based on competition
    if competition_name == "premier_division":
        gameweek_number = int(current_round.split()[-1])
        new_body = build_premier_body(fixtures, league_table, gameweek_number)
    elif competition_name == "first_division":
        gameweek_number = int(current_round.split()[-1])
        new_body = build_first_body(fixtures, league_table, gameweek_number)
    else:  # fai_cup
        new_body = build_cup_body(fixtures, current_round)

    update_reddit_post(post_id, new_body)


def main():
    """Main function - fetch live scores and update Reddit posts."""
    today = datetime.now().date()

    # Load cache to see which threads need updating
    cache = load_cache()

    if not cache:
        logger.info("No cached posts found, exiting.")
        return

    # Check if today has any matches scheduled
    has_matches_today = False
    for competition in ["premier_division", "first_division", "fai_cup"]:
        if competition in cache:
            if today.isoformat() in cache[competition].get("match_dates", []):
                has_matches_today = True
                break

    if not has_matches_today:
        logger.info("No matches scheduled for %s, exiting.", today.isoformat())
        return

    # Initialize API client with rate limiting
    api_client = APIClient(config.base_url, config.headers, rate_limiter)

    # Fetch live fixtures for all 3 competitions in one call
    league_ids = [LEAGUE_ID_PREMIER, LEAGUE_ID_FIRST, LEAGUE_ID_FAI_CUP]
    live_fixtures = get_live_fixtures(league_ids, api_client=api_client)

    if not live_fixtures:
        logger.info("No live fixtures found.")
        return

    logger.info("Found %d live fixtures", len(live_fixtures))

    # Log rate limiting stats
    stats = rate_limiter.get_stats()
    logger.info(
        "Rate limiting stats: %s/%s calls today, polling interval: %ss",
        stats['daily_calls'],
        stats['daily_limit'],
        stats['polling_interval']
    )

    # Organize fixtures by league
    fixtures_by_league = {
        LEAGUE_ID_PREMIER: [],
        LEAGUE_ID_FIRST: [],
        LEAGUE_ID_FAI_CUP: []
    }
    for fixture in live_fixtures:
        league_id = fixture["league"]["id"]
        if league_id in fixtures_by_league:
            fixtures_by_league[league_id].append(fixture)

    # Update all competitions using helper function
    competition_map = {
        "premier_division": LEAGUE_ID_PREMIER,
        "first_division": LEAGUE_ID_FIRST,
        "fai_cup": LEAGUE_ID_FAI_CUP,
    }

    for comp_name, league_id in competition_map.items():
        if comp_name in cache and fixtures_by_league[league_id]:
            update_league_thread(
                comp_name,
                cache[comp_name],
                fixtures_by_league[league_id],
                league_id
            )

    # Check if all matches are finished
    all_finished = all(
        f["fixture"]["status"]["short"] == "FT" for f in live_fixtures
    )

    if all_finished:
        logger.info("All matches finished.")
    else:
        next_poll = rate_limiter.get_polling_interval()
        logger.info("Some matches still in progress. Next poll in %ss.", next_poll)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    main()
