"""
Evaluation Script — runs test queries through the full agent pipeline
and measures accuracy, relevance, and response time.

Usage:
    python -m tests.evaluate                    # Run all tests
    python -m tests.evaluate --category normal  # Run only normal queries
    python -m tests.evaluate --limit 10         # Run first 10 tests
"""
import sys
import os
import time
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.workflow import build_workflow
from agents.state import ShoppingState
from database.mongo_client import test_connection
from vector_store import faiss_index
from database import mongo_client


def load_test_queries(category_filter=None):
    path = os.path.join(os.path.dirname(__file__), "test_queries.json")
    with open(path) as f:
        data = json.load(f)
    queries = data["test_queries"]
    if category_filter:
        queries = [q for q in queries if q.get("category") == category_filter]
    return queries


def score_result(test_case: dict, state: ShoppingState) -> dict:
    """Score a single test result against expected values."""
    prefs = state.get("preferences", {})
    recommendations = state.get("recommendations", [])
    rec_text = state.get("recommendation_text", "")

    scores = {}

    # Category accuracy
    expected_cat = test_case.get("expected_category")
    if expected_cat:
        got_cat = prefs.get("category", "")
        scores["category_correct"] = (
            expected_cat.lower() in got_cat.lower() or got_cat.lower() in expected_cat.lower()
        )
    else:
        scores["category_correct"] = None

    # Budget extraction accuracy
    expected_budget = test_case.get("expected_budget_max")
    if expected_budget:
        got_budget = prefs.get("budget_max")
        if got_budget:
            scores["budget_correct"] = abs(got_budget - expected_budget) <= expected_budget * 0.15
        else:
            scores["budget_correct"] = False
    else:
        scores["budget_correct"] = None

    # Did we get recommendations?
    scores["has_recommendations"] = len(recommendations) > 0
    scores["recommendation_count"] = len(recommendations)

    # Recommendation quality heuristics
    scores["has_prices"] = any(p.get("price") for p in recommendations)
    scores["has_images"] = any(p.get("image_url") for p in recommendations)
    scores["has_ratings"] = any(p.get("rating") for p in recommendations)
    scores["has_justification"] = len(rec_text) > 100

    return scores


def run_evaluation(queries: list, graph, limit: int = None) -> dict:
    results = []
    total = min(len(queries), limit) if limit else len(queries)

    print(f"\n{'='*60}")
    print(f"Running {total} test queries...")
    print(f"{'='*60}\n")

    for i, test_case in enumerate(queries[:total]):
        query = test_case["query"]
        print(f"[{i+1}/{total}] {query[:60]}...")

        state = ShoppingState(
            user_query=query,
            chat_history=[],
            preferences={},
            candidate_products=[],
            comparison_results=[],
            recommendations=[],
            recommendation_text="",
            error=None,
        )

        start_time = time.time()
        try:
            final_state = graph.invoke(state)
            elapsed = time.time() - start_time
            scores = score_result(test_case, final_state)
            error = final_state.get("error")
            success = True
        except Exception as e:
            elapsed = time.time() - start_time
            scores = {}
            error = str(e)
            success = False
            print(f"  ERROR: {e}")

        result = {
            "id": test_case["id"],
            "category": test_case.get("category"),
            "query": query,
            "success": success,
            "elapsed_seconds": round(elapsed, 2),
            "scores": scores,
            "error": error,
        }
        results.append(result)

        status = "✓" if success and scores.get("has_recommendations") else "✗"
        print(f"  {status} {elapsed:.1f}s | Recs: {scores.get('recommendation_count', 0)} | "
              f"Cat: {scores.get('category_correct', '?')} | Budget: {scores.get('budget_correct', '?')}")

    return _summarize(results)


def _summarize(results: list) -> dict:
    total = len(results)
    successful = [r for r in results if r["success"]]
    with_recs = [r for r in successful if r["scores"].get("has_recommendations")]

    category_checks = [r for r in results if r["scores"].get("category_correct") is not None]
    category_correct = [r for r in category_checks if r["scores"]["category_correct"]]

    budget_checks = [r for r in results if r["scores"].get("budget_correct") is not None]
    budget_correct = [r for r in budget_checks if r["scores"]["budget_correct"]]

    response_times = [r["elapsed_seconds"] for r in successful]
    avg_time = sum(response_times) / len(response_times) if response_times else 0

    summary = {
        "total_queries": total,
        "successful_runs": len(successful),
        "queries_with_recommendations": len(with_recs),
        "category_accuracy": (
            f"{len(category_correct)}/{len(category_checks)} "
            f"({100*len(category_correct)//len(category_checks) if category_checks else 0}%)"
        ),
        "budget_accuracy": (
            f"{len(budget_correct)}/{len(budget_checks)} "
            f"({100*len(budget_correct)//len(budget_checks) if budget_checks else 0}%)"
        ),
        "avg_response_time_seconds": round(avg_time, 2),
        "min_response_time": round(min(response_times), 2) if response_times else 0,
        "max_response_time": round(max(response_times), 2) if response_times else 0,
    }

    print(f"\n{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"{'='*60}\n")

    # Save report
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": summary,
        "results": results,
    }
    report_path = os.path.join(os.path.dirname(__file__), "eval_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Full report saved to: {report_path}\n")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate the Shopping Advisor pipeline")
    parser.add_argument("--category", help="Filter by query category", default=None)
    parser.add_argument("--limit", type=int, help="Max number of queries to run", default=None)
    args = parser.parse_args()

    if not test_connection():
        print("ERROR: Cannot connect to MongoDB. Check your .env file.")
        sys.exit(1)

    # Load FAISS index
    if not faiss_index.load_index():
        print("Building FAISS index from MongoDB...")
        products = mongo_client.get_all_products()
        faiss_index.build_index(products)

    graph = build_workflow()
    queries = load_test_queries(category_filter=args.category)

    if not queries:
        print(f"No queries found for category: {args.category}")
        sys.exit(1)

    run_evaluation(queries, graph, limit=args.limit)


if __name__ == "__main__":
    main()
