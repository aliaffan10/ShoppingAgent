"""
Optional utility — pre-warms the MongoDB cache with Amazon product data
so the first few queries respond faster. NOT required to run the app.

The app fetches live from Amazon on every query regardless of this cache.

Usage:
    python -m database.seed
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rainforest.client import search_products
from database.mongo_client import insert_products, product_count, test_connection
from config import SEED_CATEGORIES


def seed_database(products_per_category: int = 20) -> None:
    print("\n=== Intelligent Shopping Advisor — Database Seeder ===\n")

    if not test_connection():
        print("ERROR: Cannot connect to MongoDB. Check your MONGODB_URI in .env")
        sys.exit(1)

    print(f"Connected to MongoDB. Current product count: {product_count()}\n")

    total_inserted = 0

    for category, search_term in SEED_CATEGORIES:
        print(f"[{category.upper()}] Searching: '{search_term}'...")
        products = search_products(search_term, max_results=products_per_category)

        for product in products:
            product["category"] = category

        count = insert_products(products)
        print(f"  >> Fetched {len(products)}, inserted {count} new products\n")
        total_inserted += count

        # Be polite to the API — 1 second between requests
        time.sleep(1)

    print(f"=== Seeding complete ===")
    print(f"New products inserted: {total_inserted}")
    print(f"Total products in database: {product_count()}\n")


if __name__ == "__main__":
    seed_database()
