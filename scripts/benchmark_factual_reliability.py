from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import app
from server.tools.factual_benchmark import run_factual_benchmark


def answer(question: str) -> str:
    response = app.query_copilot(question, knowledge_mode="General knowledge only", response_mode="Fast")
    return str(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run factual reliability benchmark on 100 technical questions.")
    parser.add_argument(
        "--output",
        default="storage/benchmarks/factual_reliability_latest.json",
        help="JSON output path",
    )
    args = parser.parse_args()
    summary = run_factual_benchmark(answer, output_path=Path(args.output))
    print(f"Questions: {summary['question_count']}")
    print(f"Average factual accuracy: {summary['average_factual_accuracy']}")
    print(f"Hallucination rate: {summary['hallucination_rate']}")
    print(f"Unnecessary information rate: {summary['unnecessary_information_rate']}")
    print(f"Total seconds: {summary['total_seconds']}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
