import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
RAINFOREST_API_KEY = os.getenv("RAINFOREST_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "shopping_advisor")

# Rainforest API
RAINFOREST_BASE_URL = "https://api.rainforestapi.com/request"
AMAZON_DOMAIN = "amazon.com"

# FAISS paths
FAISS_INDEX_PATH = "vector_store/products.index"
FAISS_ID_MAP_PATH = "vector_store/id_map.json"

# Seed categories — (category_slug, amazon_search_term)
SEED_CATEGORIES = [
    ("smartphones", "best smartphones 2024"),
    ("laptops", "best laptops 2024"),
    ("headphones", "best wireless headphones noise cancelling"),
    ("tablets", "best tablets 2024"),
    ("smartwatches", "best smartwatches fitness tracker"),
    ("gaming", "best gaming laptops 2024"),
    ("earbuds", "best wireless earbuds"),
    ("cameras", "best digital cameras mirrorless"),
]
