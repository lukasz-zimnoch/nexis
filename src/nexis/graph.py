"""Parent graph — wires all four layer subgraphs with retry logic."""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from nexis.layers.output import build_output_subgraph
from nexis.layers.planning import build_planning_subgraph
from nexis.layers.research import build_research_subgraph
from nexis.layers.review import build_review_subgraph
from nexis.state import PipelineState
from nexis.telemetry import instrument_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------------


def supervisor_node(state: PipelineState) -> dict:
    """Initialize pipeline state on first run; update prompt on retry."""
    iteration = state.get("iteration", 0)
    prompt = state.get("research_prompt", state["config"].research_prompt)

    if iteration == 0:
        logger.info("Supervisor: starting pipeline (iteration 0)")
    else:
        logger.info("Supervisor: retry iteration %d", iteration)
        prompt = prompt + " (previous ideas were too generic, focus on underserved niches)"

    return {
        "research_prompt": prompt,
        "iteration": iteration,
    }


# ---------------------------------------------------------------------------
# Force-pass node: populates top_ideas when retry limit exhausted
# ---------------------------------------------------------------------------


def force_pass_node(state: PipelineState) -> dict:
    """Select the top_k ideas by score regardless of threshold."""
    scores = state.get("scores", {})
    config = state["config"]

    if not scores:
        logger.warning("force_pass_node: no scores available — proceeding with empty top_ideas")
        return {"top_ideas": []}

    sorted_ids = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    top_ideas = sorted_ids[: config.top_k]
    logger.warning(
        "force_pass_node: forcing top %d ideas by score (best=%.2f)",
        len(top_ideas),
        scores[top_ideas[0]] if top_ideas else 0,
    )
    return {"top_ideas": top_ideas}


# ---------------------------------------------------------------------------
# Retry counter node
# ---------------------------------------------------------------------------


def increment_iteration_node(state: PipelineState) -> dict:
    """Increment the iteration counter before retrying research."""
    new_iteration = state.get("iteration", 0) + 1
    logger.info("increment_iteration_node: iteration → %d", new_iteration)
    return {"iteration": new_iteration}


# ---------------------------------------------------------------------------
# Conditional routing after review layer
# ---------------------------------------------------------------------------


def should_retry(state: PipelineState) -> str:
    """Route to planning, retry, or force-pass based on top_ideas and iteration."""
    top_ideas = state.get("top_ideas", [])
    iteration = state.get("iteration", 0)
    max_retries = state["config"].max_retries

    if top_ideas:
        logger.info("should_retry: %d ideas passed threshold → planning", len(top_ideas))
        return "planning"

    if iteration < max_retries:
        logger.info(
            "should_retry: no ideas passed threshold, iteration=%d < max=%d → retry",
            iteration,
            max_retries,
        )
        return "retry"

    logger.warning(
        "should_retry: retry limit reached (iteration=%d) → force_pass",
        iteration,
    )
    return "force_pass"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


_USE_MEMORY = object()


def build_graph(checkpointer=_USE_MEMORY) -> StateGraph:
    """Build and compile the full Nexis pipeline graph.

    Args:
        checkpointer: LangGraph checkpointer instance. Defaults to MemorySaver
            when not provided. Pass None to skip checkpointing (e.g. when the
            LangGraph Platform injects its own checkpointer). For persistent
            checkpointing, pass an SqliteSaver instance.
    """
    from langgraph.checkpoint.memory import MemorySaver

    builder = StateGraph(PipelineState)

    # --- Nodes ---
    builder.add_node("supervisor", instrument_node(supervisor_node, layer_id="orchestrator"))
    builder.add_node("research", build_research_subgraph())
    builder.add_node("review", build_review_subgraph())
    builder.add_node("planning", build_planning_subgraph())
    builder.add_node("output", build_output_subgraph())
    builder.add_node("increment_iteration", instrument_node(increment_iteration_node, layer_id="orchestrator"))
    builder.add_node("force_pass", instrument_node(force_pass_node, layer_id="orchestrator"))

    # --- Edges ---
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "research")
    builder.add_edge("research", "review")
    builder.add_conditional_edges(
        "review",
        should_retry,
        {
            "planning": "planning",
            "retry": "increment_iteration",
            "force_pass": "force_pass",
        },
    )
    # Retry path: increment iteration → supervisor (refreshes prompt) → research
    builder.add_edge("increment_iteration", "supervisor")
    # Force-pass path: set top_ideas → go straight to planning
    builder.add_edge("force_pass", "planning")
    builder.add_edge("planning", "output")
    builder.add_edge("output", END)

    resolved_checkpointer = MemorySaver() if checkpointer is _USE_MEMORY else checkpointer
    return builder.compile(checkpointer=resolved_checkpointer)
