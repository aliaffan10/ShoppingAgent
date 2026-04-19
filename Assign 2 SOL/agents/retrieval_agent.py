"""
Retrieval Agent — Agent 2

Strategy:
1. Call Rainforest API LIVE using the user's search terms (primary source)
2. Cache results in MongoDB to avoid redundant API calls on repeat searches
3. Apply price/brand filters to the live results
4. Return top 20 candidates for the comparison agent
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from agents.state import ShoppingState
from database import mongo_client
from rainforest.client import search_products


def run_retrieval_agent(state: ShoppingState) -> dict:
    preferences = state["preferences"]

    category: str = preferences.get("category") or "general"
    budget_min = preferences.get("budget_min")
    budget_max = preferences.get("budget_max")
    brand = preferences.get("brand_preference")
    search_terms: list[str] = preferences.get("search_terms") or [state["user_query"]]
    sort_pref: str = preferences.get("sort_preference", "average_review")

    all_products: list[dict] = []
    seen_asins: set[str] = set()

    # ── Step 1: Fetch LIVE from Rainforest API (parallel) ──────────────────
    terms_to_fetch = search_terms[:2]

    def fetch_term(term: str) -> list[dict]:
        print(f"[RetrievalAgent] Live fetch: '{term}'")
        return search_products(term, max_results=20, sort_by=sort_pref)

    batch_results: list[list[dict]] = [[] for _ in terms_to_fetch]
    with ThreadPoolExecutor(max_workers=len(terms_to_fetch)) as executor:
        future_to_idx = {executor.submit(fetch_term, term): i for i, term in enumerate(terms_to_fetch)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                batch_results[idx] = future.result()
            except Exception as e:
                print(f"[RetrievalAgent] Fetch failed for term index {idx}: {e}")

    for api_products in batch_results:
        for p in api_products:
            p["category"] = category
            asin = p.get("asin", "")
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)
            all_products.append(p)

        # Cache in MongoDB so repeat searches don't cost extra API credits
        mongo_client.insert_products(api_products)

    # ── Step 2: Apply price and brand filters ──────────────────────────────
    filtered: list[dict] = []
    for p in all_products:
        price = p.get("price")

        if budget_max and price and price > budget_max:
            continue
        if budget_min and price and price < budget_min:
            continue
        if brand and p.get("brand"):
            if brand.lower() not in p["brand"].lower():
                continue

        filtered.append(p)

    # If brand filter removed everything, fall back to unfiltered results
    # so we always have something to show
    candidates = filtered if filtered else all_products

    # ── Step 3: If still empty, try a broader search from MongoDB cache ────
    if not candidates:
        db_fallback = mongo_client.get_products_by_filters(
            category=category if category != "general" else None,
            min_price=budget_min,
            max_price=budget_max,
            limit=20,
        )
        candidates = db_fallback

    return {"candidate_products": candidates[:20], "error": None}
