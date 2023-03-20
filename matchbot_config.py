"""Module for storing configuration data for the Matchbot script."""

class MatchbotConfig:
    """Configuration class for the Matchbot script."""
    def __init__(self):
        self.api_key = ""
        self.base_url = "https://api-football-v1.p.rapidapi.com/v3"
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
        }
        self.bot_username = ""
        self.bot_password = ""
        self.client_id = ""
        self.client_secret = ""
        self.user_agent = ""
        self.subreddit = "LeagueOfIreland"
