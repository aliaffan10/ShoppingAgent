from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from datetime import datetime, timezone
from typing import Optional
from config import MONGODB_URI, MONGODB_DB_NAME

_client: Optional[MongoClient] = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
        _db = _client[MONGODB_DB_NAME]
        # Unique index on ASIN to prevent duplicate products
        _db.products.create_index([("asin", ASCENDING)], unique=True)
    return _db


def insert_products(products: list[dict]) -> int:
    """Insert products into MongoDB, skipping duplicates. Returns count inserted."""
    db = get_db()
    inserted = 0
    for product in products:
        doc = {**product, "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            db.products.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            pass
    return inserted


def get_all_products(limit: int = 2000) -> list[dict]:
    """Fetch all products (used for building FAISS index)."""
    db = get_db()
    return list(db.products.find({}, {"_id": 0}).limit(limit))


def get_products_by_filters(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    brand: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Filtered product query — all params optional."""
    db = get_db()
    query: dict = {}

    if category:
        query["category"] = {"$regex": category, "$options": "i"}

    price_filter: dict = {}
    if min_price is not None:
        price_filter["$gte"] = min_price
    if max_price is not None:
        price_filter["$lte"] = max_price
    if price_filter:
        query["price"] = price_filter

    if brand:
        query["brand"] = {"$regex": brand, "$options": "i"}

    return list(
        db.products.find(query, {"_id": 0})
        .sort("rating", -1)
        .limit(limit)
    )


def product_count() -> int:
    """Return total number of products in the database."""
    try:
        db = get_db()
        return db.products.count_documents({})
    except Exception:
        return 0


def test_connection() -> bool:
    """Verify MongoDB connectivity."""
    try:
        db = get_db()
        db.command("ping")
        return True
    except Exception as e:
        print(f"[MongoDB] Connection failed: {e}")
        return False
