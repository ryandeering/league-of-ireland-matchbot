"""Typed data models for League of Ireland matchbot."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Team:
    """A football team with ID and display name."""

    id: int
    name: str


@dataclass
class Venue:
    """Match venue / stadium."""

    name: str


@dataclass
class MatchStatus:
    """Current match status code and elapsed minutes."""

    short: str  # NS, 1H, HT, 2H, FT, ET, AET, PEN, CANC, TBD, LIVE
    elapsed: int | None


@dataclass
class GoalEvent:
    """A single goal scored during a match."""

    player: str
    team: str
    minute: int
    is_home: bool | None  # None when source data lacks isHome flag
    is_penalty: bool
    is_own_goal: bool


@dataclass
class Fixture:
    """A single match fixture with teams, score, status, and events."""

    id: int
    date: str  # ISO 8601
    status: MatchStatus
    venue: Venue
    home: Team
    away: Team
    home_goals: int | None
    away_goals: int | None
    league_id: int
    round: str
    events: list[GoalEvent] = field(default_factory=list)
    page_url: str = ""


@dataclass
class Standing:
    """A team's position in the league table."""

    rank: int
    team: Team
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
    form: str  # raw "WDLWW" string
