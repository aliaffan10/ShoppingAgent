"""
Intelligent Shopping Advisor — Chainlit Application

The user types a natural language shopping query.
Four LangGraph agents handle it in sequence:
  1. Preference Agent  — extracts budget, category, features from the query
  2. Retrieval Agent   — fetches live Amazon products via Rainforest API
  3. Comparison Agent  — scores and ranks products against user needs
  4. Recommendation Agent — writes personalized picks with justification

Product images are displayed inline in the chat using cl.Image.
"""
import asyncio

import chainlit as cl

from graph.workflow import build_workflow
from agents.state import ShoppingState

# Compile the LangGraph state machine once at module load
_graph = build_workflow()


# ── Chat start ────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("chat_history", [])

    await cl.Message(
        content=(
            "# Your AI Shopping Advisor\n\n"
            "Just tell me what you're looking for. "
            "I'll search Amazon live, compare the options, and recommend the best picks for you — with images and prices.\n\n"
            "**Some things you can ask:**\n"
            "- Best smartphone under $500 with a great camera\n"
            "- Gaming laptop for programming and streaming\n"
            "- Wireless noise-cancelling headphones under $150\n"
            "- Budget tablet for students\n"
            "- Best smartwatch under 50,000 PKR\n\n"
            "*What are you shopping for today?*"
        )
    ).send()


# ── Message handler ───────────────────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    user_query = message.content.strip()
    chat_history: list[dict] = cl.user_session.get("chat_history", [])
    loop = asyncio.get_running_loop()

    state = ShoppingState(
        user_query=user_query,
        chat_history=chat_history,
        preferences={},
        candidate_products=[],
        comparison_results=[],
        recommendations=[],
        recommendation_text="",
        error=None,
    )

    # ── Pipeline header ───────────────────────────────────────────────────────
    await cl.Message(
        content=(
            "**Running 4-agent pipeline...**\n\n"
            "Agent 1: Preference Extraction  \n"
            "Agent 2: Product Retrieval  \n"
            "Agent 3: Comparison & Scoring  \n"
            "Agent 4: Recommendation Generation"
        ),
        author="System"
    ).send()

    # ── Agent 1: Preference Extraction ───────────────────────────────────────
    async with cl.Step(name="Agent 1 — Preference Extraction", type="run") as step:
        step.input = f'User query: "{user_query}"'
        from agents.preference_agent import run_preference_agent
        result = await loop.run_in_executor(None, run_preference_agent, state)
        state.update(result)

        prefs = result.get("preferences", {})
        budget_str = f"${prefs['budget_max']}" if prefs.get("budget_max") else "any budget"
        features   = prefs.get("must_have_features", [])
        nice       = prefs.get("nice_to_have_features", [])
        brand      = prefs.get("brand_preference") or "no preference"
        terms      = prefs.get("search_terms", [])

        step.output = (
            f"**Category detected:** {prefs.get('category', 'general')}\n"
            f"**Budget:** {budget_str}\n"
            f"**Must-have features:** {', '.join(features) if features else 'none'}\n"
            f"**Nice-to-have:** {', '.join(nice) if nice else 'none'}\n"
            f"**Brand preference:** {brand}\n"
            f"**Search terms generated:** {', '.join(terms)}"
        )

    await cl.Message(
        content=f"Agent 1 done. Extracted preferences from your query.",
        author="Agent 1: Preference Agent"
    ).send()

    # ── Agent 2: Live Product Retrieval ───────────────────────────────────────
    async with cl.Step(name="Agent 2 — Product Retrieval (Live Amazon Search)", type="run") as step:
        prefs = state.get("preferences", {})
        terms = prefs.get("search_terms", [user_query])
        step.input = f"Search terms: {', '.join(terms)}"

        from agents.retrieval_agent import run_retrieval_agent
        result = await loop.run_in_executor(None, run_retrieval_agent, state)
        state.update(result)

        products = result.get("candidate_products", [])
        names = [p.get("name", "")[:50] for p in products[:5]]
        step.output = (
            f"**Products fetched from Amazon:** {len(products)}\n"
            f"**Top results preview:**\n" +
            "\n".join(f"- {n}" for n in names) +
            (f"\n- ... and {len(products)-5} more" if len(products) > 5 else "")
        )

    if not state.get("candidate_products"):
        await cl.Message(
            content=(
                "Agent 2 found no matching products. "
                "Try adjusting your budget or using different keywords."
            ),
            author="Agent 2: Retrieval Agent"
        ).send()
        return

    await cl.Message(
        content=f"Agent 2 done. Fetched {len(state['candidate_products'])} live products from Amazon.",
        author="Agent 2: Retrieval Agent"
    ).send()

    # ── Agent 3: Comparison & Scoring ────────────────────────────────────────
    async with cl.Step(name="Agent 3 — Comparison & Scoring", type="run") as step:
        step.input = f"Scoring {len(state['candidate_products'])} products against your preferences"

        from agents.comparison_agent import run_comparison_agent
        result = await loop.run_in_executor(None, run_comparison_agent, state)
        state.update(result)

        ranked = result.get("comparison_results", [])
        top_lines = []
        for i, p in enumerate(ranked[:5], 1):
            score = p.get("overall_score", "N/A")
            name  = p.get("name", "")[:45]
            price = f"${p['price']:.2f}" if p.get("price") else "N/A"
            top_lines.append(f"{i}. {name} — Score: {score} | {price}")

        step.output = (
            f"**Products scored:** {len(ranked)}\n"
            f"**Scoring criteria:** price fit (30%), feature match (45%), rating (25%)\n\n"
            f"**Top 5 by score:**\n" + "\n".join(top_lines)
        )

    await cl.Message(
        content=f"Agent 3 done. Ranked {len(state['comparison_results'])} products by relevance score.",
        author="Agent 3: Comparison Agent"
    ).send()

    # ── Agent 4: Recommendation Generation ───────────────────────────────────
    async with cl.Step(name="Agent 4 — Recommendation Generation", type="run") as step:
        step.input = f"Generating personalized write-ups for top {min(5, len(state['comparison_results']))} products"

        from agents.recommendation_agent import run_recommendation_agent
        result = await loop.run_in_executor(None, run_recommendation_agent, state)
        state.update(result)

        recs  = result.get("recommendations", [])
        names = [r.get("name", "")[:50] for r in recs]
        step.output = (
            f"**Final recommendations:** {len(recs)}\n\n" +
            "\n".join(f"{i}. {n}" for i, n in enumerate(names, 1))
        )

    await cl.Message(
        content=f"Agent 4 done. Writing up your top {len(state['recommendations'])} picks now...",
        author="Agent 4: Recommendation Agent"
    ).send()

    recommendations: list[dict] = state.get("recommendations", [])
    intro_text = state.get("recommendation_text", "Here are my top picks:")

    # ── Stream intro message ──────────────────────────────────────────────────
    intro_msg = cl.Message(content="")
    await intro_msg.send()
    for word in intro_text.split(" "):
        await intro_msg.stream_token(word + " ")
        await asyncio.sleep(0.04)
    await intro_msg.update()

    # Pause before the first card so the intro has time to settle
    await asyncio.sleep(0.6)

    # ── Stream one card per product ───────────────────────────────────────────
    for i, product in enumerate(recommendations, 1):
        name        = product.get("name") or "Unknown Product"
        price       = product.get("price")
        currency    = product.get("currency") or "USD"
        rating      = product.get("rating")
        reviews     = product.get("ratings_total") or 0
        brand       = product.get("brand") or ""
        image_url   = (product.get("image_url") or "").strip()
        product_url = product.get("product_url") or ""
        why         = product.get("why_its_right") or ""
        best_for    = product.get("best_for") or ""
        trade_off   = product.get("trade_off") or ""

        # Format price
        if price:
            price_str = f"${price:,.2f}" if currency == "USD" else f"{currency} {price:,.2f}"
        else:
            price_str = "Check Amazon for price"

        # Format rating
        if rating:
            filled    = int(rating)
            half      = 1 if (rating - filled) >= 0.5 else 0
            empty     = 5 - filled - half
            stars     = "★" * filled + ("½" if half else "") + "☆" * empty
            rating_str = f"{stars} {rating}/5 ({reviews:,} reviews)"
        else:
            rating_str = "No rating yet"

        # Build card text
        lines = [f"### {i}. {name}"]
        if brand:
            lines.append(f"**Brand:** {brand}")
        lines.append(f"**Price:** {price_str}")
        lines.append(f"**Rating:** {rating_str}")
        if why:
            lines.append(f"\n**Why it's a great pick:** {why}")
        if best_for:
            lines.append(f"**Best for:** {best_for}")
        if trade_off:
            lines.append(f"**Trade-off:** {trade_off}")
        if product_url:
            lines.append(f"\n[View on Amazon]({product_url})")

        card_text = "\n".join(lines)

        # Attach image element upfront so it appears as text streams in
        elements = []
        if image_url:
            elements.append(
                cl.Image(
                    url=image_url,
                    name=name[:50],
                    display="inline",
                    size="large",
                )
            )

        # Stream the card text word by word with a typewriter cadence
        card_msg = cl.Message(content="", elements=elements)
        await card_msg.send()
        for word in card_text.split(" "):
            await card_msg.stream_token(word + " ")
            await asyncio.sleep(0.03)
        await card_msg.update()

        # Pause between cards so each one has time to breathe before the next
        if i < len(recommendations):
            await asyncio.sleep(1.0)

    # ── Update chat history ───────────────────────────────────────────────────
    chat_history.append({"role": "user", "content": user_query})
    chat_history.append({
        "role": "assistant",
        "content": intro_text + " " + ", ".join(
            p.get("name", "") for p in recommendations
        ),
    })
    cl.user_session.set("chat_history", chat_history[-12:])
