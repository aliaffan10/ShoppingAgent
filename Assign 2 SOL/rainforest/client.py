import requests
from typing import Optional
from config import RAINFOREST_API_KEY, RAINFOREST_BASE_URL, AMAZON_DOMAIN


def search_products(
    search_term: str,
    max_results: int = 20,
    sort_by: str = "average_review",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Search Amazon products via Rainforest API.
    Returns a list of normalized product dicts.
    """
    params = {
        "api_key": RAINFOREST_API_KEY,
        "type": "search",
        "amazon_domain": AMAZON_DOMAIN,
        "search_term": search_term,
        "sort_by": sort_by,
        "exclude_sponsored": "true",
    }

    try:
        response = requests.get(RAINFOREST_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[Rainforest] Request failed: {e}")
        return []
    except ValueError as e:
        print(f"[Rainforest] JSON parse error: {e}")
        return []

    products = []
    for item in data.get("search_results", [])[:max_results]:
        # Price can be in 'price' or 'prices' depending on the result
        price_obj = item.get("price") or {}
        if not price_obj and item.get("prices"):
            price_obj = item["prices"][0] if item["prices"] else {}

        price_value = price_obj.get("value") if isinstance(price_obj, dict) else None
        currency = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"

        # Apply price filters from caller
        if min_price is not None and price_value is not None and price_value < min_price:
            continue
        if max_price is not None and price_value is not None and price_value > max_price:
            continue

        asin = item.get("asin", "").strip()
        name = item.get("title", "").strip()

        if not asin or not name:
            continue

        product = {
            "asin": asin,
            "name": name,
            "brand": item.get("brand", ""),
            "price": price_value,
            "currency": currency,
            "rating": item.get("rating"),
            "ratings_total": item.get("ratings_total", 0) or 0,
            "image_url": item.get("image", ""),
            "product_url": item.get("link", ""),
            "features": [],
            "category": "",
        }
        products.append(product)

    return products
