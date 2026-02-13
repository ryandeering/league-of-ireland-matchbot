"""
Live score updater for League of Ireland match threads.
Polls external API for live scores and updates Reddit posts.
"""

import logging
import time
import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from tabulate import tabulate
import praw
import prawcore
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
    save_cache,
    get_fixture_dublin_date,
    apply_fallback_grounds,
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
    extract_score_from_details,
)
from rate_limiter import RateLimiter

# Caching Configuration
TABLE_CACHE_SECONDS = 1800  # Cache league tables for 30 minutes

logger = logging.getLogger(__name__)
config = MatchbotConfig()
rate_limiter = RateLimiter()

# Global cache for league tables
_table_cache: dict[int, dict[str, Any]] = {}

# Per-run cache for matchDetails scores (fixture_id -> (home, away))
_score_cache: dict[int, tuple[int, int]] = {}

# Per-run cache for match events/scorers (fixture_id -> events list)
_events_cache: dict[int, list[dict[str, Any]]] = {}

# Per-run cache of last posted body hash per post_id
_last_body: dict[str, str] = {}

# Match data client instance
client = MatchDataClient()


def _compute_body_hash(body: str) -> str:
    """Return SHA-256 hash for a post body."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _persist_body_hash(post_id: str, body_hash: str) -> None:
    """Persist post body hash to cache for cross-run deduplication."""
    try:
        cache = load_cache()
        body_hashes = cache.get("_body_hashes")
        if not isinstance(body_hashes, dict):
            body_hashes = {}
            cache["_body_hashes"] = body_hashes
        body_hashes[post_id] = body_hash
        save_cache(cache)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not persist body hash for post %s: %s", post_id, exc)


def _fetch_match_details(
    match_id: str,
) -> tuple[list[dict[str, Any]], str, tuple[Any, Any]]:
    """Fetch events, venue, and scores for a specific match.

    Args:
        match_id: Match ID to fetch details for

    Returns:
        Tuple of (events list, venue name, (home_score, away_score))
    """
    try:
        details = client.get_match_details(int(match_id))
        if details:
            events = convert_match_events(details)
            venue = extract_venue_from_details(details)
            scores = extract_score_from_details(details)
            return events, venue, scores
    except (ValueError, TypeError) as exc:
        logger.warning("Could not fetch match details: %s", exc)
    return [], "", (None, None)


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
                    events, venue, scores = _fetch_match_details(match_id)
                    converted["events"] = events
                    if events:
                        _events_cache[converted["fixture"]["id"]] = events
                    if venue:
                        converted["fixture"]["venue"]["name"] = venue
                    home_score, away_score = scores
                    if converted["goals"]["home"] is None and home_score is not None:
                        converted["goals"]["home"] = home_score
                        converted["goals"]["away"] = away_score
                    if home_score is not None:
                        _score_cache[converted["fixture"]["id"]] = (
                            home_score, away_score
                        )

                all_fixtures.append(converted)

        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return apply_fallback_grounds(all_fixtures)


def get_league_fixtures(league_id: int) -> list[dict[str, Any]]:
    """
    Fetch all fixtures for a league.

    Args:
        league_id: League ID

    Returns:
        List of fixture dictionaries in api-football compatible format (deduplicated)
    """
    fixtures_by_id: dict[Any, dict[str, Any]] = {}

    try:
        for tab in ["fixtures", "results"]:
            data = client.get_league_matches(league_id, tab=tab)
            matches = client.extract_matches(data)

            for match in matches:
                match["_league_id"] = league_id
                converted = convert_raw_match(match)
                fixture_id = converted.get("fixture", {}).get("id")
                if not fixture_id:
                    logger.warning("Fixture missing ID, skipping dedupe")
                    fixtures_by_id[id(converted)] = converted
                elif fixture_id not in fixtures_by_id or tab == "results":
                    fixtures_by_id[fixture_id] = converted

    except requests.exceptions.RequestException as exc:
        logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return apply_fallback_grounds(list(fixtures_by_id.values()))


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

    raw_table = client.get_league_table(league_id)
    if raw_table is None:
        logger.error("Error getting league table for %s", league_id)
        if league_id in _table_cache:
            logger.warning("Using stale cache for league %s", league_id)
            return _table_cache[league_id]["data"]
        return []

    table_data = convert_raw_table(raw_table)

    _table_cache[league_id] = {
        "data": table_data,
        "expires": now + TABLE_CACHE_SECONDS,
    }
    logger.info("Fetched and cached table for league %s", league_id)
    return table_data


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
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores and league table will be updated during matches*\n\n"

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
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores and league table will be updated during matches*\n\n"

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
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = (
        f"*Live scores and league table will be updated during matches*\n\n"
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
    body_hash = _compute_body_hash(new_body)
    if _last_body.get(post_id) == body_hash:
        logger.debug("Body unchanged for post %s, skipping edit", post_id)
        return True

    try:
        cache = load_cache()
        cached_hashes = cache.get("_body_hashes", {})
        cached_hash = (
            cached_hashes.get(post_id)
            if isinstance(cached_hashes, dict)
            else None
        )
        if cached_hash == body_hash:
            _last_body[post_id] = body_hash
            logger.debug(
                "Body unchanged for post %s via persisted hash, skipping edit",
                post_id,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read persisted body hash for post %s: %s", post_id, exc)

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
        _last_body[post_id] = body_hash
        _persist_body_hash(post_id, body_hash)
        logger.info("Updated post %s", post_id)
        return True
    except (
            praw.exceptions.PRAWException,
            prawcore.exceptions.PrawcoreException,
            requests.exceptions.RequestException,
    ) as e:
        logger.error("Error updating post %s: %s", post_id, e)
        return False


def _enrich_fixture_scores(fixture: dict[str, Any]) -> None:
    """Fill in missing scores from matchDetails for started/finished fixtures.

    Uses the per-run _score_cache to avoid redundant API calls.
    """
    goals = fixture.get("goals", {})
    if goals.get("home") is not None:
        return  # Already has scores

    status_short = fixture.get("fixture", {}).get("status", {}).get("short", "NS")
    if status_short in ("TBD", "NS"):
        return  # Pre-match, no scores expected

    fixture_id = fixture.get("fixture", {}).get("id")
    if not fixture_id:
        return

    # Check per-run cache first
    if fixture_id in _score_cache:
        home, away = _score_cache[fixture_id]
        fixture["goals"]["home"] = home
        fixture["goals"]["away"] = away
        return

    # Fetch from matchDetails
    details = client.get_match_details(fixture_id)
    if details:
        home_score, away_score = extract_score_from_details(details)
        if home_score is not None:
            fixture["goals"]["home"] = home_score
            fixture["goals"]["away"] = away_score
            _score_cache[fixture_id] = (home_score, away_score)


def _enrich_fixture_events(fixture: dict[str, Any]) -> None:
    """Fill in missing events from cache or matchDetails for finished fixtures.

    Uses the per-run _events_cache to preserve scorers after matches end.
    """
    if fixture.get("events"):
        return  # Already has events

    status_short = fixture.get("fixture", {}).get("status", {}).get("short", "NS")
    if status_short in ("TBD", "NS"):
        return  # Pre-match, no events expected

    fixture_id = fixture.get("fixture", {}).get("id")
    if not fixture_id:
        return

    # Check per-run cache first
    if fixture_id in _events_cache:
        fixture["events"] = _events_cache[fixture_id]
        return

    # Fetch from matchDetails for finished matches
    details = client.get_match_details(fixture_id)
    if details:
        events = convert_match_events(details)
        if events:
            fixture["events"] = events
            _events_cache[fixture_id] = events


def _get_weekly_fixtures_with_live_scores(
        league_id: int,
        match_dates: list[str],
        live_fixtures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fetch all fixtures for cached match dates and merge in live scores.

    Args:
        league_id: League ID to fetch
        match_dates: List of match dates from cache (ISO format, Dublin timezone)
        live_fixtures: List of currently live fixtures with events

    Returns:
        List of all fixtures for the week with live data merged in
    """
    all_fixtures = get_league_fixtures(league_id)

    weekly_fixtures = [
        f for f in all_fixtures
        if get_fixture_dublin_date(f) in match_dates
    ]

    live_by_id = {
        f.get("fixture", {}).get("id"): f for f in live_fixtures
    }

    merged_live_ids = set()

    merged = []
    for fixture in weekly_fixtures:
        fixture_id = fixture.get("fixture", {}).get("id")
        if fixture_id in live_by_id:
            merged.append(live_by_id[fixture_id])
            merged_live_ids.add(fixture_id)
        else:
            merged.append(fixture)

    for live_id, live_fixture in live_by_id.items():
        if live_id not in merged_live_ids:
            logger.warning(
                "Live fixture %s not in cached match_dates, including anyway",
                live_id
            )
            merged.append(live_fixture)

    # Enrich fixtures that have null scores or missing events
    for fixture in merged:
        _enrich_fixture_scores(fixture)
        _enrich_fixture_events(fixture)

    return merged


def update_league_thread(
        competition_name: str,
        cache_data: dict[str, Any],
        live_fixtures: list[dict[str, Any]],
        league_id: int,
) -> None:
    """Update a league thread with live scores and standings.

    Args:
        competition_name: Name of competition ("premier_division", etc.)
        cache_data: Cached data for this competition
        live_fixtures: List of currently live fixtures for this league
        league_id: League ID
    """
    comp_display = competition_name.replace('_', ' ').title()
    logger.info("Updating %s thread...", comp_display)

    post_id = cache_data["post_id"]
    match_dates = cache_data.get("match_dates", [])
    league_table = get_league_table(league_id)

    fixtures = _get_weekly_fixtures_with_live_scores(
        league_id, match_dates, live_fixtures
    )
    if not fixtures and match_dates:
        logger.warning(
            "Skipping %s update: API returned no fixtures but "
            "match dates are expected. Possible transient API failure.",
            comp_display,
        )
        return

    if competition_name == "premier_division":
        new_body = build_premier_body(fixtures, league_table)
    elif competition_name == "first_division":
        new_body = build_first_body(fixtures, league_table)
    else:  # fai_cup
        current_round = cache_data.get("round", "")
        new_body = build_cup_body(fixtures, current_round)

    update_reddit_post(post_id, new_body)


def _get_todays_fixtures(today, league_ids):
    """Fetch all fixtures for today (started or not).

    Args:
        today: Today's date (Dublin timezone)
        league_ids: List of league IDs to check

    Returns:
        List of today's fixtures
    """
    todays_fixtures = []
    today_str = today.isoformat()

    for league_id in league_ids:
        fixtures = get_league_fixtures(league_id)
        for fixture in fixtures:
            fixture_dublin_date = get_fixture_dublin_date(fixture)
            if fixture_dublin_date == today_str:
                todays_fixtures.append(fixture)

    return todays_fixtures


def _cleanup_finished_match_day(cache, today, competitions_today):
    """Remove today from cache when tracked competitions finish.

    Args:
        cache: The current cache dictionary
        today: Today's date
        competitions_today: Mapping of tracked competition names to league IDs
    """
    finished_statuses = {"FT", "AET", "PEN", "CANC", "ABD", "PST", "AWD", "WO"}
    today_str = today.isoformat()
    cache_updated = False

    for comp_name, league_id in competitions_today.items():
        todays_fixtures = _get_todays_fixtures(today, [league_id])
        if not todays_fixtures:
            logger.info("No %s fixtures found for today.", comp_name)
            continue

        all_finished = all(
            f.get("fixture", {}).get("status", {}).get("short") in finished_statuses
            for f in todays_fixtures
        )
        if not all_finished:
            logger.info("%s still has matches in progress or not yet finished.", comp_name)
            continue

        match_dates = cache.get(comp_name, {}).get("match_dates", [])
        if today_str in match_dates:
            match_dates.remove(today_str)
            cache_updated = True
            logger.info("Removed %s from %s match_dates", today_str, comp_name)

    if cache_updated:
        save_cache(cache)


def main():
    """Main function - fetch live scores and update Reddit posts."""
    _score_cache.clear()
    today = datetime.now(ZoneInfo("Europe/Dublin")).date()

    cache = load_cache()

    if not cache:
        logger.info("No cached posts found, exiting.")
        return

    competition_map = {
        "premier_division": LEAGUE_ID_PREMIER,
        "first_division": LEAGUE_ID_FIRST,
        "fai_cup": LEAGUE_ID_FAI_CUP,
    }

    competitions_today = {
        comp_name: league_id
        for comp_name, league_id in competition_map.items()
        if today.isoformat() in cache.get(comp_name, {}).get("match_dates", [])
    }

    if not competitions_today:
        logger.info("No matches scheduled for %s, exiting.", today.isoformat())
        return

    league_ids = list(competitions_today.values())
    live_fixtures = get_live_fixtures(league_ids)

    if not live_fixtures:
        logger.info(
            "No live fixtures found, performing final update before cleanup."
        )
        for comp_name, league_id in competitions_today.items():
            update_league_thread(comp_name, cache[comp_name], [], league_id)

        cache_for_cleanup = load_cache()
        for comp_name in competitions_today:
            if comp_name not in cache_for_cleanup and comp_name in cache:
                cache_for_cleanup[comp_name] = cache[comp_name]

        _cleanup_finished_match_day(cache_for_cleanup, today, competitions_today)
        return

    logger.info("Found %d live fixtures", len(live_fixtures))

    next_poll = rate_limiter.get_polling_interval()
    logger.info("Next poll in %ss", next_poll)

    fixtures_by_league = {league_id: [] for league_id in league_ids}
    for fixture in live_fixtures:
        league_id = fixture["league"]["id"]
        if league_id in fixtures_by_league:
            fixtures_by_league[league_id].append(fixture)

    for comp_name, league_id in competitions_today.items():
        update_league_thread(
            comp_name,
            cache[comp_name],
            fixtures_by_league[league_id],
            league_id
        )

    logger.info("Updated threads. Next poll in %ss.", next_poll)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    main()
