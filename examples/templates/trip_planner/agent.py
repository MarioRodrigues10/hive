"""Agent graph construction for City Trip Planner."""

from __future__ import annotations

from pathlib import Path

from framework.graph import Constraint, EdgeCondition, EdgeSpec, Goal, SuccessCriterion
from framework.graph.checkpoint_config import CheckpointConfig
from framework.graph.edge import GraphSpec
from framework.graph.executor import ExecutionResult, GraphExecutor
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry
from framework.runtime.agent_runtime import AgentRuntime, create_agent_runtime
from framework.runtime.event_bus import EventBus
from framework.runtime.execution_stream import EntryPointSpec

from .config import default_config, metadata
from .nodes import (
    discovery_node,
    intake_node,
    report_node,
    review_node,
    route_builder_node,
)

goal = Goal(
    id="city-trip-planning",
    name="City Trip Planning",
    description=(
        "Plan an optimised adventure or food crawl in any city — discovering the best "
        "restaurants, coffees, bars, and attractions via Google Maps, building a route "
        "with real travel times, and delivering a shareable HTML itinerary."
    ),
    success_criteria=[
        SuccessCriterion(
            id="sc-place-discovery",
            description="Discovers relevant, highly-rated places matching the user's brief",
            metric="candidates_count",
            target=">=12",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-route-built",
            description="Builds an ordered route with travel times between every stop",
            metric="route_complete",
            target="true",
            weight=0.3,
        ),
        SuccessCriterion(
            id="sc-user-approval",
            description="User reviews and approves the itinerary before the report is generated",
            metric="user_approval",
            target="true",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-report-delivered",
            description="A styled HTML itinerary is saved and served to the user",
            metric="report_delivered",
            target="true",
            weight=0.3,
        ),
    ],
    constraints=[
        Constraint(
            id="c-real-places-only",
            description="Only include places actually returned by the Google Maps API — never invent names or addresses",
            constraint_type="hard",
            category="quality",
        ),
        Constraint(
            id="c-realistic-timing",
            description="Itinerary total duration must fit within the user's available time",
            constraint_type="hard",
            category="quality",
        ),
        Constraint(
            id="c-user-checkpoint",
            description="Always present the route to the user for review before writing the final report",
            constraint_type="functional",
            category="interaction",
        ),
    ],
)


nodes = [
    intake_node,
    discovery_node,
    route_builder_node,
    review_node,
    report_node,
]

edges = [
    EdgeSpec(
        id="intake-to-discovery",
        source="intake",
        target="discovery",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
    EdgeSpec(
        id="discovery-to-route-builder",
        source="discovery",
        target="route-builder",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
    EdgeSpec(
        id="route-builder-to-review",
        source="route-builder",
        target="review",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
    ),
    EdgeSpec(
        id="review-to-route-builder",
        source="review",
        target="route-builder",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="str(needs_revision).lower() == 'true'",
        priority=1,
    ),
    # review → report (user approved)
    EdgeSpec(
        id="review-to-report",
        source="review",
        target="report",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="str(needs_revision).lower() == 'false'",
        priority=2,
    ),
    EdgeSpec(
        id="report-to-intake",
        source="report",
        target="intake",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="str(next_action).lower() == 'new_trip'",
        priority=1,
    ),
]


entry_node = "intake"
entry_points = {"start": "intake"}
pause_nodes: list[str] = []
terminal_nodes: list[str] = []

conversation_mode = "continuous"
identity_prompt = (
    "You are an enthusiastic and knowledgeable city trip planner. "
    "You combine local knowledge with real Google Maps data to craft "
    "practical, enjoyable itineraries tailored to each person's taste, "
    "budget, and available time. You never invent places."
)
loop_config = {
    "max_iterations": 100,
    "max_tool_calls_per_turn": 30,
    "max_history_tokens": 32000,
}


class TripPlannerAgent:
    """
    City Trip Planner — 5-node pipeline with a user review checkpoint.

    Flow:
        intake → discovery → route-builder → review → report
                                   ↑              |
                                   +── revision ──+  (if user wants changes)

    - intake:        gathers city, adventure type, duration, preferences
    - discovery:     searches Google Maps for candidate places
    - route-builder: selects stops and builds an optimised route with travel times
    - review:        client-facing checkpoint — user can approve or request revisions
    - report:        generates and serves a polished HTML itinerary
    """

    def __init__(self, config=None) -> None:
        self.config = config or default_config
        self.goal = goal
        self.nodes = nodes
        self.edges = edges
        self.entry_node = entry_node
        self.entry_points = entry_points
        self.pause_nodes = pause_nodes
        self.terminal_nodes = terminal_nodes
        self._graph: GraphSpec | None = None
        self._agent_runtime: AgentRuntime | None = None
        self._event_bus: EventBus | None = None
        self._tool_registry: ToolRegistry | None = None
        self._storage_path: Path | None = None

    def _build_graph(self) -> GraphSpec:
        """Build the GraphSpec."""
        return GraphSpec(
            id="city-trip-planner-graph",
            goal_id=self.goal.id,
            version="1.0.0",
            entry_node=self.entry_node,
            entry_points=self.entry_points,
            terminal_nodes=self.terminal_nodes,
            pause_nodes=self.pause_nodes,
            nodes=self.nodes,
            edges=self.edges,
            default_model=self.config.model,
            max_tokens=self.config.max_tokens,
            loop_config=loop_config,
            conversation_mode=conversation_mode,
            identity_prompt=identity_prompt,
        )

    def _setup(self) -> None:
        self._storage_path = Path.home() / ".hive" / "trip_planner"
        self._storage_path.mkdir(parents=True, exist_ok=True)

        self._event_bus = EventBus()
        self._tool_registry = ToolRegistry()

        self._tool_registry = ToolRegistry()
        mcp_config = Path(__file__).parent / "mcp_servers.json"
        if mcp_config.exists():
            self._tool_registry.load_mcp_config(mcp_config)

        llm = LiteLLMProvider(
            model=self.config.model,
            api_key=self.config.api_key,
            api_base=self.config.api_base,
        )

        tools = list(self._tool_registry.get_tools().values())
        tool_executor = self._tool_registry.get_executor()
        self._graph = self._build_graph()

        self._agent_runtime = create_agent_runtime(
            graph=self._graph,
            goal=self.goal,
            storage_path=self._storage_path,
            entry_points=[
                EntryPointSpec(
                    id="default",
                    name="Default",
                    entry_node=self.entry_node,
                    trigger_type="manual",
                    isolation_level="shared",
                )
            ],
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
            checkpoint_config=CheckpointConfig(
                enabled=True,
                checkpoint_on_node_complete=True,
                checkpoint_max_age_days=7,
                async_checkpoint=True,
            ),
        )

    async def start(self) -> None:
        if self._agent_runtime is None:
            self._setup()
        if not self._agent_runtime.is_running:
            await self._agent_runtime.start()

    async def stop(self) -> None:
        if self._agent_runtime and self._agent_runtime.is_running:
            await self._agent_runtime.stop()
        self._agent_runtime = None

    async def trigger_and_wait(
        self,
        entry_point: str = "default",
        input_data: dict | None = None,
        timeout: float | None = None,
        session_state: dict | None = None,
    ) -> ExecutionResult | None:
        if self._agent_runtime is None:
            raise RuntimeError("Agent not started. Call start() first.")
        return await self._agent_runtime.trigger_and_wait(
            entry_point_id=entry_point,
            input_data=input_data or {},
            session_state=session_state,
        )

    async def run(
        self, context: dict, session_state: dict | None = None
    ) -> ExecutionResult:
        """Convenience method — set up, run, tear down."""
        await self.start()
        try:
            result = await self.trigger_and_wait(
                "default", context, session_state=session_state
            )
            return result or ExecutionResult(success=False, error="Execution timeout")
        finally:
            await self.stop()

    def info(self) -> dict:
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "goal": {
                "name": self.goal.name,
                "description": self.goal.description,
            },
            "nodes": [n.id for n in self.nodes],
            "edges": [e.id for e in self.edges],
            "entry_node": self.entry_node,
            "entry_points": self.entry_points,
            "pause_nodes": self.pause_nodes,
            "terminal_nodes": self.terminal_nodes,
            "client_facing_nodes": [n.id for n in self.nodes if n.client_facing],
        }

    def validate(self) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        node_ids = {n.id for n in self.nodes}

        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge {edge.id}: source '{edge.source}' not found")
            if edge.target not in node_ids:
                errors.append(f"Edge {edge.id}: target '{edge.target}' not found")

        if self.entry_node not in node_ids:
            errors.append(f"Entry node '{self.entry_node}' not found")

        for terminal in self.terminal_nodes:
            if terminal not in node_ids:
                errors.append(f"Terminal node '{terminal}' not found")

        for ep_id, node_id in self.entry_points.items():
            if node_id not in node_ids:
                errors.append(
                    f"Entry point '{ep_id}' references unknown node '{node_id}'"
                )

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# Default instance
default_agent = TripPlannerAgent()
