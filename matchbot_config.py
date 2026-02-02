"""Module for storing configuration data for the Matchbot script."""


class MatchbotConfig:
    """Configuration class for the Matchbot script."""

    def __init__(self):
        self.base_url = ""
        self.headers = {
            "User-Agent": "Mozilla/5.0"
        }

        # Reddit credentials
        self.bot_username = ""
        self.bot_password = ""
        self.client_id = ""
        self.client_secret = ""
        self.user_agent = "linux:leagueofirelandbot:v1.0 (by /u/LOIMatchThreads)"
        self.subreddit = "LeagueOfIreland"
