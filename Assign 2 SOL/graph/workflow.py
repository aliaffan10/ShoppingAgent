"""
LangGraph workflow — wires all 4 agents into a directed state graph.

Flow:
  START → preference → retrieval → [conditional] → comparison → recommendation → END
                                          ↓
                                        error → END
"""
from langgraph.graph import StateGraph, END, START
from agents.state import ShoppingState
from agents.preference_agent import run_preference_agent
from agents.retrieval_agent import run_retrieval_agent
from agents.comparison_agent import run_comparison_agent
from agents.recommendation_agent import run_recommendation_agent


# ── Node functions ────────────────────────────────────────────────────────────

def preference_node(state: ShoppingState) -> dict:
    return run_preference_agent(state)


def retrieval_node(state: ShoppingState) -> dict:
    return run_retrieval_agent(state)


def comparison_node(state: ShoppingState) -> dict:
    return run_comparison_agent(state)


def recommendation_node(state: ShoppingState) -> dict:
    return run_recommendation_agent(state)


def error_node(state: ShoppingState) -> dict:
    return {
        "recommendations": [],
        "recommendation_text": (
            "I couldn't find any products matching your search. "
            "Try using different keywords, adjusting your budget, or picking a different category."
        ),
        "error": "no_products_found",
    }


# ── Conditional routing ───────────────────────────────────────────────────────

def route_after_retrieval(state: ShoppingState) -> str:
    """If retrieval found products, proceed to comparison. Otherwise error."""
    if state.get("candidate_products"):
        return "compare"
    return "error"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_workflow():
    """Compile and return the LangGraph state machine."""
    graph = StateGraph(ShoppingState)

    graph.add_node("preference", preference_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("comparison", comparison_node)
    graph.add_node("recommendation", recommendation_node)
    graph.add_node("error", error_node)

    graph.add_edge(START, "preference")
    graph.add_edge("preference", "retrieval")
    graph.add_conditional_edges(
        "retrieval",
        route_after_retrieval,
        {"compare": "comparison", "error": "error"},
    )
    graph.add_edge("comparison", "recommendation")
    graph.add_edge("recommendation", END)
    graph.add_edge("error", END)

    return graph.compile()
