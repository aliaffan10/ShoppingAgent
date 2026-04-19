"""
FAISS vector index for semantic product search.

Uses sentence-transformers (all-MiniLM-L6-v2) to encode product text,
enabling queries like "gaming laptop" to match products with relevant features
even when exact keywords don't appear in the title.
"""
import os
import json
import numpy as np
from typing import Optional

_model = None
_index = None
_id_map: list[str] = []
_initialized = False

INDEX_PATH = "vector_store/products.index"
ID_MAP_PATH = "vector_store/id_map.json"


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print("[FAISS] Loading sentence-transformers model (first run downloads ~80MB)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[FAISS] Model loaded.")
    return _model


def _product_to_text(product: dict) -> str:
    """Convert a product dict to a single searchable string."""
    parts = [
        product.get("name", ""),
        product.get("brand", ""),
        product.get("category", ""),
        " ".join(product.get("features", [])),
    ]
    return " ".join(p for p in parts if p).strip()


def build_index(products: list[dict]) -> None:
    """Build and persist a FAISS index from a list of product dicts."""
    global _index, _id_map, _initialized

    if not products:
        print("[FAISS] No products provided — skipping index build.")
        return

    import faiss

    model = _get_model()
    texts = [_product_to_text(p) for p in products]

    print(f"[FAISS] Encoding {len(texts)} products...")
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)
    embeddings = embeddings.astype(np.float32)

    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(embeddings)

    dim = embeddings.shape[1]
    _index = faiss.IndexFlatIP(dim)
    _index.add(embeddings)

    _id_map = [p.get("asin", str(i)) for i, p in enumerate(products)]

    # Persist to disk
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    faiss.write_index(_index, INDEX_PATH)
    with open(ID_MAP_PATH, "w") as f:
        json.dump(_id_map, f)

    _initialized = True
    print(f"[FAISS] Index built and saved — {len(products)} products indexed.")


def load_index() -> bool:
    """Load a previously saved FAISS index from disk. Returns True if successful."""
    global _index, _id_map, _initialized

    if not (os.path.exists(INDEX_PATH) and os.path.exists(ID_MAP_PATH)):
        return False

    try:
        import faiss
        _index = faiss.read_index(INDEX_PATH)
        with open(ID_MAP_PATH) as f:
            _id_map = json.load(f)
        _initialized = True
        print(f"[FAISS] Index loaded from disk — {len(_id_map)} products.")
        return True
    except Exception as e:
        print(f"[FAISS] Failed to load index: {e}")
        return False


def search(query: str, top_k: int = 20) -> list[str]:
    """
    Return a ranked list of ASINs semantically similar to the query.
    Returns empty list if index is not initialized.
    """
    global _index, _id_map

    if _index is None or not _id_map:
        return []

    try:
        import faiss
        model = _get_model()
        query_embedding = model.encode([query], show_progress_bar=False).astype(np.float32)
        faiss.normalize_L2(query_embedding)

        k = min(top_k, _index.ntotal)
        if k == 0:
            return []

        _, indices = _index.search(query_embedding, k)
        return [
            _id_map[idx]
            for idx in indices[0]
            if 0 <= idx < len(_id_map)
        ]
    except Exception as e:
        print(f"[FAISS] Search error: {e}")
        return []


def is_ready() -> bool:
    return _initialized and _index is not None
