# City Trip Planner

Plans food crawls, coffee hops, sightseeing tours, and nightlife adventures in any city. Discovers real places via Google Maps, builds an optimised route with live travel times, and delivers a polished HTML itinerary you can save and share.

## Nodes

| Node | Type | Client-facing | Description |
|------|------|:---:|-------------|
| `intake` | `event_loop` | ✅ | Chats with the user to collect city, adventure type, duration, travel mode, budget, and constraints |
| `discovery` | `event_loop` | — | Searches Google Maps with targeted queries to build a longlist of 12–20 rated candidate places |
| `route-builder` | `event_loop` | — | Selects the best stops, fetches place details, and calls Google Maps Directions to compute an optimised ordered route with travel times |
| `review` | `event_loop` | ✅ | Presents the itinerary to the user as a scannable text summary; lets them swap stops or adjust timing before the report is written |
| `report` | `event_loop` | ✅ | Generates a styled HTML itinerary with stop cards, Google Maps deep links, ratings, opening hours, and a trip summary — then serves it to the user |

## Flow

```
intake → discovery → route-builder → review → report
                           ↑             │
                           └─ revision ──┘  (if user requests changes)
                                                  │
                                        report → intake  (if user wants a new trip)
```

## Adventure types

| Type | Places searched |
|------|----------------|
| 🍜 Food crawl | Restaurants, street food, local specialties |
| ☕ Coffee hop | Specialty coffee, bakeries, brunch spots |
| 🏛️ Sightseeing | Landmarks, museums, viewpoints, parks |
| 🍸 Nightlife | Bars, cocktail lounges, rooftop terraces |
| 🛍️ Mixed | A curated mix of all of the above |

## Tools used

| Tool | Node | Purpose |
|------|------|---------|
| `maps_place_search` | `discovery` | Text-based place search with type, price, and location filters |
| `maps_place_details` | `route-builder` | Enriches key stops with opening hours, website, phone, and editorial summary |
| `maps_directions` | `route-builder` | Computes an optimised multi-stop walking/transit/driving route |
| `maps_distance_matrix` | `route-builder` | Fallback for leg distances/times if Directions fails |
| `save_data` | `report` | Creates the HTML itinerary file |
| `append_data` | `report` | Appends each stop card section-by-section to stay within token limits |
| `serve_file_to_user` | `report` | Delivers the file as a clickable link and opens it in the browser |

## Requirements

- **Google Maps API key** — set `GOOGLE_MAPS_API_KEY` in your environment.
  Enable the following APIs in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
  - Places API
  - Directions API
  - Distance Matrix API

## Running

### TUI (recommended — interactive conversation)

```bash
uv run python -m examples.templates.trip_planner tui
```

### CLI shell (interactive, no TUI)

```bash
uv run python -m examples.templates.trip_planner shell
```

### Single-shot run

```bash
uv run python -m examples.templates.trip_planner run --request "food crawl in Tokyo, Shinjuku area, 5 hours, walking, $$"
```

### Other commands

```bash
# Show agent info
uv run python -m examples.templates.trip_planner info

# Validate agent structure
uv run python -m examples.templates.trip_planner validate
```

## Output

The agent produces a `trip_itinerary.html` file that includes:

- Hero header with adventure type, city, total stops, distance, and travel mode
- One **stop card** per place with:
  - Name, category tag, star rating, and price level
  - Full address with a direct **Open in Google Maps** deep link
  - Editorial description and a curated highlight sentence
  - Website, phone number, and opening hours (when available)
  - Suggested arrival time and visit duration
- **Leg connectors** between stops showing distance and walking/transit time
- **Trip summary** table with totals

## Example prompts

- *"Coffee hop in Lisbon, half day, walking, $$"*
- *"Best ramen and izakayas in Shinjuku, Tokyo — 6 hours, walking"*
- *"Sightseeing in Rome — 8 hours, mix of free and paid attractions, no driving"*
- *"Rooftop bars and cocktail bars in Manhattan, Friday night, 4 hours"*
- *"Mixed food and culture day in Barcelona — 7 hours, public transit, mid-range"*
