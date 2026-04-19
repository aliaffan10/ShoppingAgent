"""
Recommendation Agent — Agent 4

Takes the top-ranked products from the Comparison Agent and uses Gemini
to generate per-product justifications returned as a structured list.
Each item contains: why_its_right, best_for, trade_off.
app.py uses this to render a formatted card per product.
"""
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from agents.state import ShoppingState
from config import GEMINI_API_KEY

_SYSTEM_PROMPT = """You are an expert shopping advisor. For each product provided, write a short personalized justification based on the user's query.

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {
    "asin": "...",
    "why_its_right": "2-3 sentences explaining why this fits the user's specific needs and budget",
    "best_for": "one short phrase describing the ideal buyer",
    "trade_off": "one honest limitation or downside"
  }
]

Rules:
- Be specific — reference the user's budget or features directly
- Never invent specs not in the product name
- Keep each justification concise and helpful
- If price is missing, note that price varies
"""


def run_recommendation_agent(state: ShoppingState) -> dict:
    preferences = state["preferences"]
    comparison_results = state["comparison_results"]
    user_query = state["user_query"]

    if not comparison_results:
        return {
            "recommendations": [],
            "recommendation_text": (
                "I couldn't find products matching your criteria. "
                "Try adjusting your budget or using different keywords."
            ),
            "error": None,
        }

    top_products = comparison_results[:5]

    product_info = [
        {
            "rank": i + 1,
            "asin": p.get("asin", ""),
            "name": p.get("name", "")[:80],
            "brand": p.get("brand", ""),
            "price": p.get("price"),
            "rating": p.get("rating"),
            "ratings_total": p.get("ratings_total", 0),
            "match_reason": p.get("match_reason", ""),
        }
        for i, p in enumerate(top_products)
    ]

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f'User query: "{user_query}"\n\n'
                f"Preferences: {json.dumps(preferences, indent=2)}\n\n"
                f"Products: {json.dumps(product_info, indent=2)}"
            )
        ),
    ]

    justification_map: dict[str, dict] = {}
    try:
        response = llm.invoke(messages)
        content = response.content.strip()

        if "```" in content:
            parts = content.split("```")
            for part in parts:
                stripped = part.strip().lstrip("json").strip()
                if stripped.startswith("["):
                    content = stripped
                    break

        justifications: list[dict] = json.loads(content)
        justification_map = {j["asin"]: j for j in justifications}

    except Exception as e:
        print(f"[RecommendationAgent] Gemini error: {e}")

    # Merge justifications into product dicts
    enriched: list[dict] = []
    for p in top_products:
        asin = p.get("asin", "")
        j = justification_map.get(asin, {})
        enriched.append({
            **p,
            "why_its_right": j.get("why_its_right", p.get("match_reason", "")),
            "best_for": j.get("best_for", ""),
            "trade_off": j.get("trade_off", ""),
        })

    # Build a simple intro summary (not the full text — cards handle details)
    intro = f"Here are the top {len(enriched)} picks for **\"{user_query}\"**:"

    return {
        "recommendations": enriched,
        "recommendation_text": intro,
        "error": None,
    }
