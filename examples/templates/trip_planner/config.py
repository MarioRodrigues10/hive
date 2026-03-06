"""Runtime configuration for City Trip Planner."""

from dataclasses import dataclass

from framework.config import RuntimeConfig

default_config = RuntimeConfig()


@dataclass
class AgentMetadata:
    name: str = "City Trip Planner"
    version: str = "1.0.0"
    description: str = (
        "Plans adventures and food crawls in any city by discovering restaurants, cafes, "
        "bars, and attractions via Google Maps, then building an optimized route with "
        "estimated travel times, distances, and a shareable HTML itinerary."
    )
    intro_message: str = (
        "Hi! I'm your city trip planner. Tell me a city and what kind of adventure "
        "you're after — a food crawl, coffee hop, sightseeing tour, or a mix — and I'll "
        "build you a step-by-step route with real places, travel times, and a full "
        "itinerary you can save and share. Where are we going?"
    )


metadata = AgentMetadata()
