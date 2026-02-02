"""
Integration tests for Reddit posting and editing.

These tests require real Reddit credentials and should be run manually.
They post to a test subreddit, verify, edit, and clean up.

Usage:
    # Set environment variables or use .env file
    export REDDIT_CLIENT_ID=your_client_id
    export REDDIT_CLIENT_SECRET=your_client_secret
    export REDDIT_USERNAME=your_bot_username
    export REDDIT_PASSWORD=your_bot_password
    export TEST_SUBREDDIT=your_test_subreddit  # e.g., "testingground4bots"

    python -m pytest tests/test_reddit_integration.py -v -s
"""

import os
import time
import unittest
from datetime import datetime

import praw
from praw.exceptions import PRAWException


def get_reddit_client():
    """Create Reddit client from environment variables."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")

    if not all([client_id, client_secret, username, password]):
        return None

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent="LOI-Matchbot-Integration-Test/1.0",
    )


def get_test_subreddit():
    """Get test subreddit name from environment."""
    return os.environ.get("TEST_SUBREDDIT", "testingground4bots")


class TestRedditConnection(unittest.TestCase):
    """Test basic Reddit connection."""

    def setUp(self):
        self.reddit = get_reddit_client()
        if not self.reddit:
            self.skipTest("Reddit credentials not configured")

    def test_connection_authenticated(self):
        """Test that we can authenticate with Reddit."""
        try:
            user = self.reddit.user.me()
            self.assertIsNotNone(user)
            print(f"Authenticated as: {user.name}")
        except PRAWException as e:
            self.fail(f"Failed to authenticate: {e}")

    def test_can_access_subreddit(self):
        """Test that we can access the test subreddit."""
        subreddit_name = get_test_subreddit()
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            # Access a property to verify it exists
            display_name = subreddit.display_name
            self.assertEqual(display_name.lower(), subreddit_name.lower())
            print(f"Can access subreddit: r/{display_name}")
        except PRAWException as e:
            self.fail(f"Failed to access subreddit: {e}")


class TestRedditPostingCycle(unittest.TestCase):
    """Test full posting and editing cycle."""

    def setUp(self):
        self.reddit = get_reddit_client()
        if not self.reddit:
            self.skipTest("Reddit credentials not configured")
        self.subreddit_name = get_test_subreddit()
        self.created_post_id = None

    def tearDown(self):
        """Clean up: delete test post if created."""
        if self.created_post_id and self.reddit:
            try:
                post = self.reddit.submission(id=self.created_post_id)
                post.delete()
                print(f"Cleaned up test post: {self.created_post_id}")
            except PRAWException as e:
                print(f"Warning: Could not delete test post: {e}")

    def test_full_post_edit_cycle(self):
        """Test creating a post, editing it, and verifying changes."""
        subreddit = self.reddit.subreddit(self.subreddit_name)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Step 1: Create initial post
        initial_body = (
            f"# LOI Matchbot Integration Test\n\n"
            f"**Test started:** {timestamp}\n\n"
            f"## Initial Fixtures\n\n"
            f"| Home | Score | Away |\n"
            f"|------|-------|------|\n"
            f"| Shamrock Rovers | vs | Bohemian FC |\n"
            f"| St Patrick's Athletic | vs | Shelbourne |\n\n"
            f"*Waiting for live scores...*"
        )

        title = f"[TEST] LOI Match Thread - {timestamp}"

        try:
            post = subreddit.submit(title, selftext=initial_body)
            self.created_post_id = post.id
            print(f"\nCreated post: https://reddit.com{post.permalink}")
        except PRAWException as e:
            self.fail(f"Failed to create post: {e}")

        # Wait for Reddit to process
        time.sleep(2)

        # Step 2: Verify post was created
        try:
            post = self.reddit.submission(id=self.created_post_id)
            self.assertIn("LOI Matchbot Integration Test", post.selftext)
            self.assertIn("Shamrock Rovers", post.selftext)
            print("Verified initial post content")
        except PRAWException as e:
            self.fail(f"Failed to verify post: {e}")

        # Step 3: Edit post with "live" scores
        updated_body = (
            f"# LOI Matchbot Integration Test\n\n"
            f"**Test started:** {timestamp}\n\n"
            f"## Live Fixtures\n\n"
            f"| Home | Score | Away | Status |\n"
            f"|------|-------|------|--------|\n"
            f"| Shamrock Rovers | 2-1 | Bohemian FC | 67' |\n"
            f"| St Patrick's Athletic | 0-0 | Shelbourne | HT |\n\n"
            f"**Shamrock Rovers:** Gaffney 23', Burke 45'\n"
            f"**Bohemian FC:** Mandroiu 34'\n\n"
            f"*Live scores updated at {datetime.now().strftime('%H:%M:%S')}*"
        )

        try:
            post.edit(updated_body)
            print("Edited post with live scores")
        except PRAWException as e:
            self.fail(f"Failed to edit post: {e}")

        # Wait for edit to process
        time.sleep(2)

        # Step 4: Verify edit was applied
        try:
            post = self.reddit.submission(id=self.created_post_id)
            post_content = post.selftext

            # Check scores are present
            self.assertIn("2-1", post_content)
            self.assertIn("67'", post_content)
            self.assertIn("HT", post_content)

            # Check scorers are present
            self.assertIn("Gaffney 23'", post_content)
            self.assertIn("Burke 45'", post_content)
            self.assertIn("Mandroiu 34'", post_content)

            print("Verified edited post content")
            print("\n--- Final Post Content ---")
            print(post_content[:500])
            print("---")

        except PRAWException as e:
            self.fail(f"Failed to verify edit: {e}")

    def test_multiple_rapid_edits(self):
        """Test that multiple rapid edits work correctly."""
        subreddit = self.reddit.subreddit(self.subreddit_name)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create post
        initial_body = f"# Rapid Edit Test\n\nStarted: {timestamp}\n\nScore: 0-0"
        title = f"[TEST] Rapid Edit Test - {timestamp}"

        try:
            post = subreddit.submit(title, selftext=initial_body)
            self.created_post_id = post.id
            print("\nCreated post for rapid edit test")
        except PRAWException as e:
            self.fail(f"Failed to create post: {e}")

        # Simulate rapid score updates (like multiple goals in quick succession)
        scores = [
            ("1-0", "Goal! 12'"),
            ("1-1", "Goal! 15'"),
            ("2-1", "Goal! 23'"),
            ("2-2", "Goal! 45'"),
        ]

        for score, event in scores:
            time.sleep(1)  # Small delay between edits
            body = (
                f"# Rapid Edit Test\n\n"
                f"Started: {timestamp}\n\n"
                f"Score: {score}\n\n"
                f"Latest: {event}"
            )
            try:
                post = self.reddit.submission(id=self.created_post_id)
                post.edit(body)
                print(f"  Updated to {score}")
            except PRAWException as e:
                self.fail(f"Failed to edit post: {e}")

        # Verify final state
        time.sleep(2)
        post = self.reddit.submission(id=self.created_post_id)
        self.assertIn("2-2", post.selftext)
        self.assertIn("Goal! 45'", post.selftext)
        print("All rapid edits successful")


class TestRedditPostFormatting(unittest.TestCase):
    """Test that post formatting renders correctly."""

    def setUp(self):
        self.reddit = get_reddit_client()
        if not self.reddit:
            self.skipTest("Reddit credentials not configured")
        self.subreddit_name = get_test_subreddit()
        self.created_post_id = None

    def tearDown(self):
        if self.created_post_id and self.reddit:
            try:
                post = self.reddit.submission(id=self.created_post_id)
                post.delete()
            except PRAWException:
                pass

    def test_markdown_table_formatting(self):
        """Test that markdown tables render properly."""
        subreddit = self.reddit.subreddit(self.subreddit_name)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build a post similar to actual match thread
        body = """*Live scores will be updated during matches*

## Friday, February 6th

| Home | Score | Away | Venue | Status |
|:-----|:-----:|:-----|:------|:------:|
| Derry City | 2-1 | Sligo Rovers | The Brandywell | 67' |
| Galway United | 0-0 | Drogheda United | Eamonn Deacy Park | HT |
| Waterford FC | 1-3 | Shelbourne | RSC | 78' |
| Shamrock Rovers | 1-0 | Dundalk | Tallaght Stadium | 23' |

**Derry City:** McEleney 12', Patching 58'
**Sligo Rovers:** Keena 34' (pen)

**Shelbourne:** Farrugia 15', 45', Boyd 67'
**Waterford FC:** Power 52'

## League Table, as of Round 0

| Pos | Team | P | W | D | L | GF | GA | GD | Pts | Form |
|:---:|:-----|:-:|:-:|:-:|:-:|:--:|:--:|:--:|:---:|:----:|
| 1 | Shamrock Rovers | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - |
| 2 | Shelbourne | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - |


Welcome to the discussion thread for the League of Ireland Premier Division.

*This post was created by a bot.*
"""

        title = f"[TEST] Table Format Test - {timestamp}"

        try:
            post = subreddit.submit(title, selftext=body)
            self.created_post_id = post.id
            print("\nCreated formatting test post")
            print(f"View at: https://reddit.com{post.permalink}")
            print("\nVerify tables render correctly in browser/app")

            # Basic verification that content is there
            time.sleep(2)
            post = self.reddit.submission(id=self.created_post_id)
            self.assertIn("Derry City", post.selftext)
            self.assertIn("2-1", post.selftext)
            self.assertIn("McEleney 12'", post.selftext)

        except PRAWException as e:
            self.fail(f"Failed: {e}")


class TestDryRun(unittest.TestCase):
    """Test dry-run functionality without actually posting."""

    def test_build_post_body_premier(self):
        """Test building Premier Division post body."""
        from match_client import convert_raw_match
        from live_updater import build_premier_body

        # Sample fixtures
        raw_fixtures = [
            {
                "id": "123",
                "round": "1",
                "home": {"id": "1", "name": "Shamrock Rovers"},
                "away": {"id": "2", "name": "Bohemian FC"},
                "status": {
                    "utcTime": "2026-02-06T19:45:00Z",
                    "started": True,
                    "finished": False,
                    "score": {"home": 2, "away": 1},
                    "liveTime": {"short": "67"}
                },
                "_league_id": 126
            }
        ]

        converted = [convert_raw_match(f) for f in raw_fixtures]

        league_table = []

        body = build_premier_body(converted, league_table)

        print("\n--- Generated Post Body ---")
        print(body)
        print("---")

        # Verify structure
        self.assertIn("Live scores will be updated", body)
        self.assertIn("Shamrock Rovers", body)
        self.assertIn("2-1", body)
        self.assertIn("Welcome to the discussion thread", body)

    def test_build_post_body_cup(self):
        """Test building FAI Cup post body."""
        from match_client import convert_raw_match
        from live_updater import build_cup_body

        raw_fixtures = [
            {
                "id": "456",
                "round": "Quarter-finals",
                "home": {"id": "1", "name": "St Patrick's Athletic"},
                "away": {"id": "2", "name": "Shelbourne"},
                "status": {
                    "utcTime": "2026-08-15T19:45:00Z",
                    "started": True,
                    "finished": False,
                    "score": {"home": 1, "away": 1},
                    "liveTime": {"short": "HT"}
                },
                "_league_id": 219
            }
        ]

        converted = [convert_raw_match(f) for f in raw_fixtures]

        body = build_cup_body(converted, "Quarter-finals")

        print("\n--- Generated FAI Cup Body ---")
        print(body)
        print("---")

        self.assertIn("Quarter-finals", body)
        self.assertIn("St Patrick's Athletic", body)
        self.assertIn("FAI Cup", body)


if __name__ == "__main__":
    unittest.main()
