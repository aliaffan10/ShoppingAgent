"""
Preference Agent — Agent 1

Parses the user's natural language query and extracts structured preferences:
budget, category, required features, brand preference, and search terms.
"""
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from agents.state import ShoppingState
from config import GEMINI_API_KEY

_SYSTEM_PROMPT = """You are a shopping preference extractor. Parse the user's query and return ONLY a valid JSON object — no markdown, no explanation, just the JSON.

Output format:
{
  "budget_min": <number in USD or null>,
  "budget_max": <number in USD or null>,
  "category": <one of: "smartphones" | "laptops" | "headphones" | "tablets" | "smartwatches" | "gaming" | "earbuds" | "cameras" | "general">,
  "must_have_features": [<list of key features user explicitly requires>],
  "nice_to_have_features": [<list of preferred but optional features>],
  "brand_preference": <brand name string or null>,
  "search_terms": [<1-3 concise Amazon search strings>],
  "sort_preference": <"price_low_to_high" | "average_review" | "bestseller_rankings">
}

Rules:
- PKR to USD: divide by 280 (e.g. 100,000 PKR = ~$357)
- "cheap" / "budget" → budget_max: 200
- "mid-range" → budget_max: 600
- "premium" / "high-end" / "flagship" → budget_min: 800
- "best" with no budget → sort_preference: "average_review"
- Always produce at least 1 search_term
- If no budget → both null
- For gaming laptops → category: "gaming"
"""


def run_preference_agent(state: ShoppingState) -> dict:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    )

    user_query = state["user_query"]
    chat_history = state.get("chat_history", [])

    # Include recent conversation context so follow-up queries work
    context_lines = []
    for msg in chat_history[-4:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:200]
        context_lines.append(f"{role}: {content}")

    context_block = ""
    if context_lines:
        context_block = f"\nPrevious conversation:\n" + "\n".join(context_lines) + "\n"

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"{context_block}User query: {user_query}"),
    ]

    try:
        response = llm.invoke(messages)
        content = response.content.strip()

        # Strip markdown code fences if present
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("{"):
                    content = stripped
                    break
            else:
                content = parts[1].strip().lstrip("json").strip()

        preferences = json.loads(content)

    except (json.JSONDecodeError, Exception) as e:
        print(f"[PreferenceAgent] Parsing error: {e}")
        preferences = {
            "budget_min": None,
            "budget_max": None,
            "category": "general",
            "must_have_features": [],
            "nice_to_have_features": [],
            "brand_preference": None,
            "search_terms": [user_query],
            "sort_preference": "average_review",
        }

    return {"preferences": preferences, "error": None}
