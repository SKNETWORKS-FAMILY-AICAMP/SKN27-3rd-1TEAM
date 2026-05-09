from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.db_search import (
    DEFAULT_EMBEDDING_MODEL,
    ReliabilityFilter,
    SearchMode,
    create_default_embedding_fn,
    db_search_rag_node,
    run_db_search_rag,
)


SMOKE_QUESTIONS = [
    "보스 공격력과 방어율 무시 옵션은 언제 챙겨야 해?",
    "6차 HEXA 코어 강화 우선순위를 알려줘",
    "5차 코어 강화는 어떤 순서로 하면 좋아?",
    "이벤트 보상으로 장비 성장을 어떻게 하면 좋아?",
    "메소를 아끼면서 스펙업하는 방법 알려줘",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="DB Search RAG smoke test.")
    parser.add_argument("--query", default=SMOKE_QUESTIONS[0])
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--mode",
        choices=["text", "vector", "hybrid"],
        default="text",
        help="Use text by default to avoid model downloads in quick checks.",
    )
    parser.add_argument(
        "--reliability-filter",
        choices=["ALL", "HIGH_ONLY"],
        default="ALL",
    )
    parser.add_argument("--dsn")
    parser.add_argument("--with-embedding", action="store_true")
    args = parser.parse_args()

    embedding_fn = (
        create_default_embedding_fn(DEFAULT_EMBEDDING_MODEL)
        if args.with_embedding
        else None
    )
    mode: SearchMode = args.mode
    reliability_filter: ReliabilityFilter = args.reliability_filter

    response = run_db_search_rag(
        query=args.query,
        embedding_fn=embedding_fn,
        top_k=args.top_k,
        reliability_filter=reliability_filter,
        mode=mode,
        dsn=args.dsn,
    )
    state = db_search_rag_node(
        {
            "user_query": args.query,
            "character_name": "smoke-test",
            "world_name": "smoke-test",
        },
        embedding_fn=embedding_fn,
        top_k=args.top_k,
        reliability_filter=reliability_filter,
        mode=mode,
        dsn=args.dsn,
    )

    print(f"query: {response.query}")
    print(f"retrieved_docs: {len(response.retrieved_docs)}")
    print(f"state_keys: {sorted(state.keys())}")
    print()
    print(response.context)


if __name__ == "__main__":
    main()
