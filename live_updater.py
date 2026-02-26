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

from models import Fixture, GoalEvent, Standing, Venue
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
    to_fixture,
    to_standing,
    to_events,
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

# Per-run cache for match events/scorers (fixture_id -> GoalEvent list)
_events_cache: dict[int, list[GoalEvent]] = {}

# Per-run cache of last posted body hash per post_id
_last_body: dict[str, str] = {}

# Match data client instance
client = MatchDataClient()


def _serialize_events(events: list[GoalEvent]) -> list[dict[str, Any]]:
    """Convert GoalEvents to JSON-serialisable dicts."""
    return [{"player": e.player, "team": e.team, "minute": e.minute,
             "is_home": e.is_home, "is_penalty": e.is_penalty,
             "is_own_goal": e.is_own_goal} for e in events]


def _deserialize_events(raw: list[dict[str, Any]]) -> list[GoalEvent]:
    """Convert JSON dicts back to GoalEvents."""
    return [GoalEvent(**d) for d in raw]


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


def _persist_events(fixture_id: int, events: list[GoalEvent]) -> None:
    """Save match events to file cache so they survive across runs."""
    try:
        cache = load_cache()
        match_events = cache.get("_match_events")
        if not isinstance(match_events, dict):
            match_events = {}
            cache["_match_events"] = match_events
        match_events[str(fixture_id)] = _serialize_events(events)
        save_cache(cache)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not persist events for fixture %s: %s", fixture_id, exc)


def _load_persisted_events(fixture_id: int) -> list[GoalEvent]:
    """Load match events from file cache."""
    try:
        cache = load_cache()
        match_events = cache.get("_match_events", {})
        persisted_list = match_events.get(str(fixture_id), [])
        return _deserialize_events(persisted_list)
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _fetch_match_details(
    match_id: str,
    page_url: str = "",
) -> tuple[list[GoalEvent], str, tuple[Any, Any]]:
    """Fetch events, venue, and scores for a specific match.

    Args:
        match_id: Match ID to fetch details for
        page_url: Optional page URL slug for page-based fetching

    Returns:
        Tuple of (GoalEvent list, venue name, (home_score, away_score))
    """
    try:
        details = client.get_match_details(int(match_id), page_url=page_url)
        if details:
            events = to_events(details)
            venue = extract_venue_from_details(details)
            scores = extract_score_from_details(details)
            return events, venue, scores
    except (ValueError, TypeError) as exc:
        logger.warning("Could not fetch match details: %s", exc)
    return [], "", (None, None)


def get_live_fixtures(
    league_ids: list[int],
    match_dates: set[str] | None = None,
) -> list[Fixture]:
    """
    Fetch live and recently-finished fixtures for multiple leagues.

    Live matches are always included. Finished matches are included only
    when their Dublin-local date falls within *match_dates* so that
    scorers / events are preserved in the thread after full-time.

    Args:
        league_ids: list of league IDs to fetch
        match_dates: optional set of ISO date strings (Dublin tz) to
            scope finished-match inclusion

    Returns:
        List of Fixture    """
    all_fixtures: list[Fixture] = []

    for league_id in league_ids:
        try:
            data = client.get_league_matches(league_id, tab="fixtures")
            matches = client.extract_matches(data)

            for match in matches:
                status = match.get("status", {})
                if not status.get("started"):
                    continue

                match["_league_id"] = league_id
                converted = to_fixture(match)

                # Skip finished matches outside the tracked date range
                if status.get("finished"):
                    if not match_dates:
                        continue
                    if get_fixture_dublin_date(converted) not in match_dates:
                        continue

                match_id = match.get("id")
                if match_id:
                    events, venue, scores = _fetch_match_details(
                        match_id, page_url=match.get("pageUrl", "")
                    )
                    converted.events = events
                    if events:
                        _events_cache[converted.id] = events
                        _persist_events(converted.id, events)
                    if venue:
                        converted.venue = Venue(name=venue)
                    home_score, away_score = scores
                    if converted.home_goals is None and home_score is not None:
                        converted.home_goals = home_score
                        converted.away_goals = away_score
                    if home_score is not None:
                        _score_cache[converted.id] = (
                            home_score, away_score
                        )

                all_fixtures.append(converted)

        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return apply_fallback_grounds(all_fixtures)


def get_league_fixtures(league_id: int) -> list[Fixture]:
    """
    Fetch all fixtures for a league.

    Args:
        league_id: League ID

    Returns:
        List of Fixtures (deduplicated)
    """
    fixtures_by_id: dict[Any, Fixture] = {}

    try:
        for tab in ["fixtures", "results"]:
            data = client.get_league_matches(league_id, tab=tab)
            matches = client.extract_matches(data)

            for match in matches:
                match["_league_id"] = league_id
                converted = to_fixture(match)
                fixture_id = converted.id
                if not fixture_id:
                    logger.warning("Fixture missing ID, skipping dedupe")
                    fixtures_by_id[id(converted)] = converted
                elif fixture_id not in fixtures_by_id or tab == "results":
                    fixtures_by_id[fixture_id] = converted

    except requests.exceptions.RequestException as exc:
        logger.error("Error fetching fixtures for league %s: %s", league_id, exc)

    return apply_fallback_grounds(list(fixtures_by_id.values()))


def get_league_table(league_id: int) -> list[Standing]:
    """Return league table for a specific league with caching.

    Tables are cached for 30 minutes as they only change after matches finish.

    Args:
        league_id: League ID (126=Premier, 218=First)

    Returns:
        List of Standing    """
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

    table_data = [to_standing(row) for row in raw_table]

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


def build_premier_body(
    matches_data: list[Fixture],
    league_table: list[Standing],
) -> str:
    """Build the body text for Premier Division post."""
    matches_by_date: dict[str, list[Fixture]] = {}
    for match in matches_data:
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores will be updated during matches*\n\n"

    for date, matches_list in sorted(matches_by_date.items()):
        body += _format_match_date_section(date, matches_list)

    table_data = [
        [
            item.rank,
            normalise_team_name(item.team.name),
            item.played,
            item.won,
            item.drawn,
            item.lost,
            item.goals_for,
            item.goals_against,
            item.goal_diff,
            item.points,
            get_last_matches(item.team.id, league_table),
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


def build_first_body(
    matches_data: list[Fixture],
    league_table: list[Standing],
) -> str:
    """Build the body text for First Division post."""
    matches_by_date: dict[str, list[Fixture]] = {}
    for match in matches_data:
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores will be updated during matches*\n\n"

    for date, matches_list in sorted(matches_by_date.items()):
        body += _format_match_date_section(date, matches_list)

    table_data = [
        [
            item.rank,
            normalise_team_name(item.team.name),
            item.played,
            item.won,
            item.drawn,
            item.lost,
            item.goals_for,
            item.goals_against,
            item.goal_diff,
            item.points,
            get_last_matches(item.team.id, league_table),
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


def build_cup_body(matches_data: list[Fixture], current_round: str) -> str:
    """Build the body text for FAI Cup post."""
    matches_by_date: dict[str, list[Fixture]] = {}
    for match in matches_data:
        date = get_fixture_dublin_date(match)
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


def _enrich_fixture(fixture: Fixture) -> None:
    """Fill in missing scores and events from matchDetails.

    Makes a single API call to fetch both, using per-run caches to
    avoid redundant requests.
    """
    if fixture.status.short in ("TBD", "NS"):
        return

    fixture_id = fixture.id
    if not fixture_id:
        return

    needs_scores = fixture.home_goals is None
    needs_events = not fixture.events

    # Satisfy from caches first
    if needs_scores and fixture_id in _score_cache:
        home, away = _score_cache[fixture_id]
        fixture.home_goals = home
        fixture.away_goals = away
        needs_scores = False

    if needs_events and fixture_id in _events_cache:
        fixture.events = _events_cache[fixture_id]
        needs_events = False

    # Check persisted file cache for events saved during live play
    if needs_events:
        persisted = _load_persisted_events(fixture_id)
        if persisted:
            fixture.events = persisted
            _events_cache[fixture_id] = persisted
            needs_events = False

    if not needs_scores and not needs_events:
        return

    # Single API call for whatever is still missing
    page_url = fixture.page_url
    details = client.get_match_details(fixture_id, page_url=page_url)
    if not details:
        return

    if needs_scores:
        home_score, away_score = extract_score_from_details(details)
        if home_score is not None:
            fixture.home_goals = home_score
            fixture.away_goals = away_score
            _score_cache[fixture_id] = (home_score, away_score)

    if needs_events:
        events = to_events(details)
        if events:
            fixture.events = events
            _events_cache[fixture_id] = events
            _persist_events(fixture_id, events)


def _get_weekly_fixtures_with_live_scores(
        league_id: int,
        match_dates: list[str],
        live_fixtures: list[Fixture]
) -> list[Fixture]:
    """Fetch all fixtures for cached match dates and merge in live scores.

    Args:
        league_id: League ID to fetch
        match_dates: List of match dates from cache (ISO format, Dublin timezone)
        live_fixtures: List of currently live Fixtures with events

    Returns:
        List of all Fixtures for the week with live data merged in
    """
    all_fixtures = get_league_fixtures(league_id)

    weekly_fixtures = [
        f for f in all_fixtures
        if get_fixture_dublin_date(f) in match_dates
    ]

    live_by_id = {
        f.id: f for f in live_fixtures
    }

    merged_live_ids: set[int] = set()

    merged: list[Fixture] = []
    for fixture in weekly_fixtures:
        fixture_id = fixture.id
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
        _enrich_fixture(fixture)

    return merged


def update_league_thread(
        competition_name: str,
        cache_data: dict[str, Any],
        live_fixtures: list[Fixture],
        league_id: int,
) -> None:
    """Update a league thread with live scores and standings.

    Args:
        competition_name: Name of competition ("premier_division", etc.)
        cache_data: Cached data for this competition
        live_fixtures: List of currently live Fixtures for this league
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
        List of today's Fixture    """
    todays_fixtures: list[Fixture] = []
    today_str = today.isoformat()

    for league_id in league_ids:
        fixtures = get_league_fixtures(league_id)
        for fixture in fixtures:
            fixture_dublin_date = get_fixture_dublin_date(fixture)
            if fixture_dublin_date == today_str:
                todays_fixtures.append(fixture)

    return todays_fixtures


def _cleanup_finished_match_day(cache, today, competitions_today):
    """Mark today as completed when tracked competitions finish.

    Adds today to ``completed_dates`` so the updater stops polling for this
    day, but keeps ``match_dates`` intact so the post body still includes
    all fixtures for the full week.

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
            f.status.short in finished_statuses
            for f in todays_fixtures
        )
        if not all_finished:
            logger.info("%s still has matches in progress or not yet finished.", comp_name)
            continue

        comp_cache = cache.get(comp_name, {})
        completed = comp_cache.get("completed_dates", [])
        if today_str not in completed:
            completed.append(today_str)
            comp_cache["completed_dates"] = completed
            cache_updated = True
            logger.info("Marked %s as completed for %s", today_str, comp_name)

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

    today_str = today.isoformat()
    competitions_today: dict[str, int] = {}
    for comp_name, league_id in competition_map.items():
        comp_cache = cache.get(comp_name, {})
        if today_str in comp_cache.get("match_dates", []):
            if today_str not in comp_cache.get("completed_dates", []):
                competitions_today[comp_name] = league_id

    if not competitions_today:
        logger.info("No matches scheduled for %s, exiting.", today.isoformat())
        return

    league_ids = list(competitions_today.values())

    all_match_dates: set[str] = set()
    for comp_name in competitions_today:
        all_match_dates.update(cache[comp_name].get("match_dates", []))

    live_fixtures = get_live_fixtures(league_ids, match_dates=all_match_dates)

    if live_fixtures:
        logger.info("Found %d active fixtures", len(live_fixtures))

    fixtures_by_league: dict[int, list[Fixture]] = {league_id: [] for league_id in league_ids}
    for fixture in live_fixtures:
        league_id = fixture.league_id
        if league_id in fixtures_by_league:
            fixtures_by_league[league_id].append(fixture)

    for comp_name, league_id in competitions_today.items():
        update_league_thread(
            comp_name,
            cache[comp_name],
            fixtures_by_league[league_id],
            league_id
        )

    # Check if all matches for today are done and mark day complete
    cache_for_cleanup = load_cache()
    for comp_name in competitions_today:
        if comp_name not in cache_for_cleanup and comp_name in cache:
            cache_for_cleanup[comp_name] = cache[comp_name]
    _cleanup_finished_match_day(cache_for_cleanup, today, competitions_today)

    next_poll = rate_limiter.get_polling_interval()
    logger.info("Updated threads. Next poll in %ss.", next_poll)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    main()
