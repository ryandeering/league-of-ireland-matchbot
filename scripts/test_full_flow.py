#!/usr/bin/env python3
"""
End-to-end test: post to r/test using actual module code, then simulate live update.
"""

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import praw

sys.path.insert(0, '.')

from matchbot_config import MatchbotConfig
from match_client import LEAGUE_ID_PREMIER
from common import (
    parse_match_datetime,
    filter_weekly_matches,
    get_match_date_range,
    load_cache,
    save_cache,
)
from premier_division import (
    get_matches_for_league,
    get_league_table,
    build_post_body,
)
from live_updater import (
    get_league_fixtures,
    get_league_table as get_live_table,
    build_premier_body,
    _get_fixture_dublin_date,
)

config = MatchbotConfig()


def main():
    now = datetime.now(ZoneInfo("Europe/Dublin"))
    today = now.date()

    print("=" * 60)
    print("FULL FLOW TEST - r/test")
    print("=" * 60)

    # Step 1: Use premier_division.get_matches_for_league()
    print("\n1. Fetching matches (premier_division.get_matches_for_league)...")
    all_matches = get_matches_for_league()
    print(f"   Total: {len(all_matches)} matches")

    # Step 2: Filter weekly matches
    print("\n2. Filtering weekly matches (common.filter_weekly_matches)...")
    weekly_matches = filter_weekly_matches(all_matches, today)
    if not weekly_matches:
        print("   No matches this week, using next 5 upcoming for test")
        upcoming = [m for m in all_matches
                    if parse_match_datetime(m["fixture"]["date"]).date() >= today]
        weekly_matches = sorted(upcoming, key=lambda m: m["fixture"]["date"])[:5]
    print(f"   Weekly: {len(weekly_matches)} matches")

    # Step 3: Get date range
    first_date, last_date = get_match_date_range(weekly_matches)
    title = (
        f"[TEST] LOI Premier Division - Fixtures / "
        f"{first_date.strftime('%d-%m-%Y')} to {last_date.strftime('%d-%m-%Y')}"
    )
    print(f"   Title: {title}")

    # Step 4: Get league table
    print("\n3. Fetching league table (premier_division.get_league_table)...")
    league_table = get_league_table()
    print(f"   Teams: {len(league_table)}")

    # Step 5: Build post body
    print("\n4. Building body (premier_division.build_post_body)...")
    body = build_post_body(weekly_matches, league_table)
    print(f"   Length: {len(body)} chars")

    # Step 6: Post to Reddit
    print("\n5. Posting to r/test...")
    reddit = praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        username=config.bot_username,
        password=config.bot_password,
        user_agent=config.user_agent,
    )
    post = reddit.subreddit("test").submit(title, selftext=body)
    post_id = post.id
    print(f"   Posted: https://reddit.com/r/test/comments/{post_id}")

    # Step 7: Save to cache
    print("\n6. Saving cache (common.save_cache)...")
    cache = load_cache()
    match_dates = sorted({
        parse_match_datetime(m["fixture"]["date"]).date().isoformat()
        for m in weekly_matches
    })
    cache["premier_division"] = {
        "post_id": post_id,
        "match_dates": match_dates,
        "posted_at": now.isoformat()
    }
    save_cache(cache)
    print(f"   match_dates: {match_dates}")

    # Step 8: Simulate live update
    print("\n7. Waiting 5s before live update simulation...")
    time.sleep(5)

    print("\n8. Simulating live update (live_updater functions)...")

    # Use live_updater.get_league_fixtures (with dedupe)
    fresh_fixtures = get_league_fixtures(LEAGUE_ID_PREMIER)
    print(f"   Fetched {len(fresh_fixtures)} fixtures (deduplicated)")

    # Filter by cached match_dates using Dublin timezone
    weekly_fresh = [
        f for f in fresh_fixtures
        if _get_fixture_dublin_date(f) in match_dates
    ]
    print(f"   Filtered to {len(weekly_fresh)} weekly fixtures")

    # Get fresh table
    fresh_table = get_live_table(LEAGUE_ID_PREMIER)

    # Build updated body using live_updater.build_premier_body
    updated_body = build_premier_body(weekly_fresh, fresh_table)

    # Add marker to show update worked
    updated_body = updated_body.replace(
        "*Live scores will be updated during matches*",
        "*Live scores will be updated during matches* ✅ **UPDATE SUCCESSFUL**"
    )

    # Edit post
    post.edit(updated_body)
    print("   Post edited!")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print(f"https://reddit.com/r/test/comments/{post_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
