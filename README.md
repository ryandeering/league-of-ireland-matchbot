# Matchbot for League of Ireland Subreddit
This repository contains the source code for Matchbot, a Python script created by Ryan Deering (github.com/ryandeering) to automatically generate and post discussion threads for the League of Ireland Premier Division matches on the League of Ireland subreddit.

![image](https://user-images.githubusercontent.com/37181720/226486687-bf9e23d0-582e-4dd8-b16a-5259fafa4df6.png)

## Features
- Grabs the current gameweek and match fixtures using the football-data API from API-FOOTBALL.
- Grabs the league table.
- Generates a formatted Reddit post including match fixtures, kickoff times, grounds, and league table.
- Submits the generated post to the League of Ireland subreddit.

I've wrote the code to not be too tightly coupled with the League of Ireland. However, this is my project, and ultimately I just need it to do what I need it to do so there's stuff that can be improved like the welcome message being hardcoded. If you wish to make the code more league-agnostic, be my guest, however it should be pretty easy to switch it out for a new league if need be.

## Configuration
To use this script, you will need to edit the matchbot_config.py file with the necessary credentials gotten from Reddit like the `client_id` and `client_secret`.

## Usage
You need Python 3.6 or higher.

You can run `pip install -r requirements.txt` for quick installation of the dependencies.

To run one of the scripts, simply execute the following command:
`python premier_division.py`

Matchbot will then automatically generate and post the discussion thread for the current gameweek's matches in the League of Ireland subreddit (or whichever you've configured it to.)

## Acknowledgements
- [PRAW (Python Reddit API Wrapper)](https://praw.readthedocs.io/en/stable/)
- [Requests](https://requests.readthedocs.io/en/latest/)
- [Tabulate](https://pypi.org/project/tabulate/)
- [League of Ireland subreddit](https://www.reddit.com/r/LeagueOfIreland/)

## Contributing
Any suggestions or improvements? Please feel free to create an issue or submit a pull request on the GitHub repository. I'd appreciate any effort to make the code more decoupled from the league.
