"""Test match data API integration with live data."""

from match_client import (
    MatchDataClient,
    LEAGUE_ID_PREMIER,
    LEAGUE_ID_FIRST,
    LEAGUE_ID_FAI_CUP,
    convert_raw_table,
    convert_match_events,
)

# Additional leagues for testing
LEAGUE_ID_EPL = 47  # English Premier League


def check_league_live(client, league_id, league_name):
    """Check a league for live matches."""
    print(f"\n--- {league_name} (ID: {league_id}) ---")
    try:
        data = client.get_league_matches(league_id, tab="fixtures")
        all_matches = data.get("fixtures", {}).get("allMatches", [])
        if not all_matches:
            all_matches = client.extract_matches(data)

        live_count = 0
        for match in all_matches:
            status = match.get("status", {})
            if status.get("started") and not status.get("finished"):
                live_count += 1
                match["_league_id"] = league_id

                home = match.get("home", {}).get("name", "?")
                away = match.get("away", {}).get("name", "?")
                score = status.get("score", {})
                live_time = status.get("liveTime", {}).get("short", "")
                match_id = match.get("id")

                home_score = score.get('home', 0)
                away_score = score.get('away', 0)
                print(f"  LIVE: {home} {home_score}-{away_score} {away} ({live_time})")

                if match_id:
                    try:
                        details = client.get_match_details(int(match_id))
                        events = convert_match_events(details)
                        if events:
                            for e in events:
                                player = e["player"]["name"]
                                minute = e["time"]["elapsed"]
                                detail = e.get("detail", "")
                                if detail == "Penalty":
                                    suffix = " (P)"
                                elif detail == "Own Goal":
                                    suffix = " (OG)"
                                else:
                                    suffix = ""
                                print(f"        Goal: {player} {minute}'{suffix}")
                    except Exception:
                        pass

        if live_count == 0:
            upcoming = [m for m in all_matches[:3] if not m.get("status", {}).get("started")]
            if upcoming:
                print("  No live matches. Upcoming:")
                for m in upcoming:
                    home = m.get("home", {}).get("name", "?")
                    away = m.get("away", {}).get("name", "?")
                    print(f"    {home} vs {away}")
            else:
                print("  No upcoming matches found")

    except Exception as e:
        print(f"  Error: {e}")


def main():
    """Test match data API with real data."""
    client = MatchDataClient()

    print("=" * 60)
    print("Testing Match Data API Integration")
    print("=" * 60)

    # Check English Premier League first (most likely to have live games)
    check_league_live(client, LEAGUE_ID_EPL, "English Premier League")

    # Check League of Ireland
    check_league_live(client, LEAGUE_ID_PREMIER, "LOI Premier Division")
    check_league_live(client, LEAGUE_ID_FIRST, "LOI First Division")
    check_league_live(client, LEAGUE_ID_FAI_CUP, "FAI Cup")

    # Test League Table
    print("\n--- LOI Premier Division Table ---")
    try:
        table = client.get_league_table(LEAGUE_ID_PREMIER)
        converted_table = convert_raw_table(table)
        print(f"Found {len(converted_table)} teams")

        if converted_table:
            print(f"  {'Pos':<4} {'Team':<25} {'P':<3} {'W':<3} {'D':<3} {'L':<3} {'Pts':<4}")
            print("  " + "-" * 50)
            for team in converted_table[:5]:
                print(
                    f"  {team['rank']:<4} "
                    f"{team['team']['name'][:24]:<25} "
                    f"{team['all']['played']:<3} "
                    f"{team['all']['win']:<3} "
                    f"{team['all']['draw']:<3} "
                    f"{team['all']['lose']:<3} "
                    f"{team['points']:<4}"
                )
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
