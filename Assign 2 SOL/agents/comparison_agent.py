"""
Comparison Agent — Agent 3

Uses Gemini to score each candidate product against the user's preferences
across three dimensions: price fit, feature match, and rating quality.
Returns a ranked list with scores.
"""
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from agents.state import ShoppingState
from config import GEMINI_API_KEY

_SYSTEM_PROMPT = """You are a product comparison expert. Score each product against the user's preferences.

Scoring criteria (0–10 each):
- price_score: How well does the price fit the budget?
  - No price data → 5
  - Within budget → 8-10 (closer to budget_max = higher)
  - Slightly over budget → 3-5
  - Way over budget → 0-2
- feature_score: How well does the product name/brand match the user's required features?
  - 9-10 = strong match on must-have features
  - 5-7 = partial match
  - 0-4 = poor match
- rating_score: Based on the product's star rating
  - 4.5+ → 9-10
  - 4.0-4.4 → 7-8
  - 3.5-3.9 → 5-6
  - No rating → 5
- overall_score: Weighted average (price 30%, feature 45%, rating 25%)

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {
    "asin": "...",
    "price_score": 8,
    "feature_score": 9,
    "rating_score": 8,
    "overall_score": 8.6,
    "match_reason": "One sentence on why this fits the user's needs"
  }
]
"""


def run_comparison_agent(state: ShoppingState) -> dict:
    preferences = state["preferences"]
    products = state["candidate_products"]

    if not products:
        return {"comparison_results": [], "error": "No candidate products to compare"}

    # Build concise summaries — only what LLM needs, cap at 15 to stay within token limit
    product_summaries = [
        {
            "asin": p.get("asin", ""),
            "name": p.get("name", "")[:80],
            "brand": p.get("brand", ""),
            "price": p.get("price"),
            "currency": p.get("currency", "USD"),
            "rating": p.get("rating"),
            "ratings_total": p.get("ratings_total", 0),
        }
        for p in products[:15]
    ]

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"User preferences:\n{json.dumps(preferences, indent=2)}\n\n"
                f"Products to score:\n{json.dumps(product_summaries, indent=2)}"
            )
        ),
    ]

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

        scores: list[dict] = json.loads(content)

    except (json.JSONDecodeError, Exception) as e:
        print(f"[ComparisonAgent] Scoring failed ({e}), falling back to rating sort")
        # Graceful fallback — sort by rating descending
        fallback = sorted(
            products,
            key=lambda p: (p.get("rating") or 0),
            reverse=True,
        )
        for p in fallback:
            p.setdefault("match_reason", "Highly rated product")
        return {"comparison_results": fallback, "error": None}

    # Merge scores back into full product dicts
    product_map = {p.get("asin", ""): p for p in products}
    comparison_results: list[dict] = []

    for score in sorted(scores, key=lambda s: s.get("overall_score", 0), reverse=True):
        asin = score.get("asin", "")
        if asin in product_map:
            merged = {**product_map[asin], **score}
            comparison_results.append(merged)

    # Include any products that Gemini may have missed (add at the end)
    scored_asins = {s.get("asin") for s in scores}
    for p in products:
        if p.get("asin") not in scored_asins:
            comparison_results.append(p)

    return {"comparison_results": comparison_results, "error": None}
