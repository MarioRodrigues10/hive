"""
City Trip Planner - Plan food crawls, coffee hops, and sightseeing adventures.

Discovers real places via Google Maps, builds an optimised walking/transit route,
and delivers a polished HTML itinerary with stop-by-stop directions and timings.
"""

from __future__ import annotations

from .agent import TripPlannerAgent, default_agent, edges, goal, nodes
from .config import AgentMetadata, RuntimeConfig, default_config, metadata

__version__ = "1.0.0"

__all__ = [
    "TripPlannerAgent",
    "default_agent",
    "goal",
    "nodes",
    "edges",
    "RuntimeConfig",
    "AgentMetadata",
    "default_config",
    "metadata",
]
