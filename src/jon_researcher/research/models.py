"""Shared models for research/search providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchSearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class ResearchFetchedPage:
    url: str
    title: str
    text: str
    source: str = ""
