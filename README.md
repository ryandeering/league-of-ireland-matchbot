# Matchbot for League of Ireland Subreddit
This repository contains the source code for Matchbot, a Python script created by Ryan Deering (github.com/ryandeering) to automatically generate and post discussion threads for the League of Ireland Premier Division matches on the League of Ireland subreddit.

![image](https://user-images.githubusercontent.com/37181720/226485597-c45b2bda-41f8-4133-9193-07846c3a6d91.png)

## Features
- Grabs the current gameweek and match fixtures using the football-data API from API-FOOTBALL.
- Grabs the league table.
- Generates a formatted Reddit post including match fixtures, kickoff times, grounds, and league table.
- Submits the generated post to the League of Ireland subreddit.

I've wrote the code to not be too tightly coupled with the League of Ireland. However, this is my project, and ultimately I just need it to do what I need it to do so there's stuff that can be improved like the welcome message being hardcoded. If you wish to make the code more league-agnostic, be my guest, however it should be pretty easy to switch it out for a new league if need be.

## Configuration
To use this script, you will need to edit the matchbot_config.py file with the necessary credentials gotten from Reddit like the `client_id` and `client_secret`.

## Usage
To run one of the scripts, simply execute the following command:
`python premier_division.py`


Matchbot will then automatically generate and post the discussion thread for the current gameweek's matches in the League of Ireland subreddit (or whichever you've configured it to.)
