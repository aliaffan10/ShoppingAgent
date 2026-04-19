from typing import TypedDict, List, Optional


class ShoppingState(TypedDict):
    """Shared state passed between all LangGraph agent nodes."""

    # Input
    user_query: str
    chat_history: List[dict]

    # Agent 1 output
    preferences: dict

    # Agent 2 output
    candidate_products: List[dict]

    # Agent 3 output
    comparison_results: List[dict]

    # Agent 4 output
    recommendations: List[dict]
    recommendation_text: str

    # Error handling
    error: Optional[str]
