"""
Live score updater for League of Ireland match threads.
Polls external API for live scores and updates Reddit posts.
"""

import logging
import time
from datetime import datetime
from typing import Any

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
    load_cache,
)
from match_client import (
    MatchDataClient,
    LEAGUE_ID_PREMIER,
    LEAGUE_ID_FIRST,
    LEAGUE_ID_FAI_CUP,
    convert_raw_match,
    convert_raw_table,
    convert_match_events,
    extract_venue_from_details,
)
from rate_limiter import RateLimiter

# Caching Configuration
TABLE_CACHE_SECONDS = 1800  # Cache league tables for 30 minutes

logger = logging.getLogger(__name__)
config = MatchbotConfig()
rate_limiter = RateLimiter()

# Global cache for league tables
_table_cache: dict[int, dict[str, Any]] = {}

# Match data client instance
client = MatchDataClient()


def _fetch_match_details(match_id: str) -> tuple[list[dict[str, Any]], str]:
    """Fetch events and venue for a specific match.

    Args:
        match_id: Match ID to fetch details for

    Returns:
        Tuple of (events list, venue name)
    """
    try:
        details = client.get_match_details(int(match_id))
        if details:
            events = convert_match_events(details)
            venue = extract_venue_from_details(details)
            return events, venue
    except (ValueError, TypeError) as exc:
        logger.warning("Could not fetch match details: %s", exc)
    return [], ""


def _is_live_match(match: dict[str, Any]) -> bool:
    """Check if a match is currently live.

    Args:
        match: Raw match data

    Returns:
        True if match is live (started but not finished)
    """
    status = match.get("status", {})
    return status.get("started") and not status.get("finished")


def get_live_fixtures(league_ids: list[int]) -> list[dict[str, Any]]:
    """
    Fetch live fixtures for multiple leagues.

    Args:
        league_ids: list of league IDs to fetch

    Returns:
        List of fixture dictionaries in api-football compatible format
    """
    all_fixtures = []

    for league_id in league_ids:
        try:
            data = client.get_league_matches(league_id, tab="fixtures")
            matches = client.extract_matches(data)

            for match in matches:
                if not _is_live_match(match):
                    continue

                match["_league_id"] = league_id
                converted = convert_raw_match(match)

                match_id = match.get("id")
                if match_id:
                    events, venue = _fetch_match_details(match_id)
                    converted["events"] = events
                    if venue:
                        converted["fixture"]["venue"]["name"] = venue

                all_fixtures.append(converted)

        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return all_fixtures


def get_league_fixtures(league_id: int) -> list[dict[str, Any]]:
    """
    Fetch all fixtures for a league.

    Args:
        league_id: League ID

    Returns:
        List of fixture dictionaries in api-football compatible format
    """
    fixtures = []

    try:
        for tab in ["fixtures", "results"]:
            data = client.get_league_matches(league_id, tab=tab)
            matches = client.extract_matches(data)

            for match in matches:
                match["_league_id"] = league_id
                converted = convert_raw_match(match)
                fixtures.append(converted)

    except requests.exceptions.RequestException as exc:
        logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return fixtures


def get_league_table(league_id: int) -> list[dict[str, Any]]:
    """Return league table for a specific league with caching.

    Tables are cached for 30 minutes as they only change after matches finish.

    Args:
        league_id: League ID (126=Premier, 218=First)

    Returns:
        List of team standings dictionaries in api-football format
    """
    now = time.time()

    if league_id in _table_cache:
        cache_entry = _table_cache[league_id]
        if now < cache_entry["expires"]:
            logger.debug(
                "Using cached table for league %s (expires in %ds)",
                league_id,
                int(cache_entry["expires"] - now)
            )
            return cache_entry["data"]

    try:
        raw_table = client.get_league_table(league_id)
        table_data = convert_raw_table(raw_table)

        _table_cache[league_id] = {
            "data": table_data,
            "expires": now + TABLE_CACHE_SECONDS,
        }
        logger.info("Fetched and cached table for league %s", league_id)
        return table_data

    except requests.exceptions.RequestException as exc:
        logger.error("Error getting league table for %s: %s", league_id, exc)

        if league_id in _table_cache:
            logger.warning("Using stale cache for league %s", league_id)
            return _table_cache[league_id]["data"]
        return []


def _format_match_date_section(date_str, matches_list):
    """Format matches for a single date into a markdown section.

    All matches in one table with scorers in a column.
    """
    date_extracted = datetime.strptime(date_str, "%Y-%m-%d")
    date_header = date_extracted.strftime(
        f"%A, %B {ordinal_suffix(date_extracted.day)}"
    )
    section = f"## {date_header}\n\n"

    # All matches in one table (scorers are now a column)
    match_rows = [format_live_fixture(match) for match in matches_list]
    match_table = tabulate(
        match_rows, headers=match_table_headers, tablefmt='pipe'
    )
    section += f"{match_table}\n\n"

    return section


def build_premier_body(matches_data, league_table):
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

    if league_table:
        body += "## Current League Table\n\n"
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


def build_first_body(matches_data, league_table):
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

    if league_table:
        body += "## Current League Table\n\n"
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
        body += f"### {date_header}\n\n"

        # All matches in one table (scorers are now a column)
        match_rows = [format_live_fixture(match) for match in matches_list]
        match_table = tabulate(
            match_rows, headers=match_table_headers, tablefmt='pipe'
        )
        body += f"{match_table}\n\n"

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
        cache_data: dict[str, Any],
        fixtures: list[dict[str, Any]],
        league_id: int,
) -> None:
    """Update a league thread with live scores and standings.

    Args:
        competition_name: Name of competition ("premier_division", etc.)
        cache_data: Cached data for this competition
        fixtures: List of fixtures for this league
        league_id: League ID
    """
    comp_display = competition_name.replace('_', ' ').title()
    logger.info("Updating %s thread...", comp_display)

    post_id = cache_data["post_id"]
    league_table = get_league_table(league_id)

    if competition_name == "premier_division":
        new_body = build_premier_body(fixtures, league_table)
    elif competition_name == "first_division":
        new_body = build_first_body(fixtures, league_table)
    else:  # fai_cup
        current_round = cache_data.get("round", "")
        new_body = build_cup_body(fixtures, current_round)

    update_reddit_post(post_id, new_body)


def main():
    """Main function - fetch live scores and update Reddit posts."""
    today = datetime.now().date()

    cache = load_cache()

    if not cache:
        logger.info("No cached posts found, exiting.")
        return

    has_matches_today = False
    for competition in ["premier_division", "first_division", "fai_cup"]:
        if competition in cache:
            if today.isoformat() in cache[competition].get("match_dates", []):
                has_matches_today = True
                break

    if not has_matches_today:
        logger.info("No matches scheduled for %s, exiting.", today.isoformat())
        return

    league_ids = [LEAGUE_ID_PREMIER, LEAGUE_ID_FIRST, LEAGUE_ID_FAI_CUP]
    live_fixtures = get_live_fixtures(league_ids)

    if not live_fixtures:
        logger.info("No live fixtures found.")
        return

    logger.info("Found %d live fixtures", len(live_fixtures))

    next_poll = rate_limiter.get_polling_interval()
    logger.info("Next poll in %ss", next_poll)

    fixtures_by_league = {
        LEAGUE_ID_PREMIER: [],
        LEAGUE_ID_FIRST: [],
        LEAGUE_ID_FAI_CUP: []
    }
    for fixture in live_fixtures:
        league_id = fixture["league"]["id"]
        if league_id in fixtures_by_league:
            fixtures_by_league[league_id].append(fixture)

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

    all_finished = all(
        f["fixture"]["status"]["short"] == "FT" for f in live_fixtures
    )

    if all_finished:
        logger.info("All matches finished.")
    else:
        logger.info("Some matches still in progress. Next poll in %ss.", next_poll)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    main()
