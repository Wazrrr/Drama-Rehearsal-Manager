"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scene:
    name: str
    actors: tuple[str, ...]
    duration_slots: int = 1


@dataclass(frozen=True)
class FeasibleSlot:
    day_index: int
    start_slot: int
    duration_slots: int
