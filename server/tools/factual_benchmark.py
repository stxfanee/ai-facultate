from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class FactualBenchmarkQuestion:
    question: str
    expected_facts: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    category: str = "technical"


@dataclass(frozen=True)
class FactualBenchmarkResult:
    question: str
    category: str
    elapsed_seconds: float
    factual_accuracy: float
    hallucination_flag: bool
    unnecessary_information_flag: bool
    missing_expected_facts: tuple[str, ...]
    forbidden_claims_found: tuple[str, ...]
    answer_chars: int


CP_PS_HP_REGRESSION = FactualBenchmarkQuestion(
    question="Care este diferen?a dintre CP, PS ?i hp ?i cum se convertesc ?n kW?",
    expected_facts=(
        "CP = PS",
        "0.73549875",
        "1.3596216",
        "0.74569987",
        "1.3410221",
    ),
    forbidden_claims=("0.98632", "1 PS ~= 0.98632 kW", "1 PS ~= 0.98632 kW"),
    category="unit_conversion",
)


def default_technical_questions() -> list[FactualBenchmarkQuestion]:
    questions = [CP_PS_HP_REGRESSION]
    seeds = [
        "Transforma 1 kW in CP.",
        "Transforma 100 km/h in m/s.",
        "Transforma 1 bar in Pa.",
        "Transforma 1 kWh in joule.",
        "Transforma 25 Celsius in Kelvin.",
    ]
    while len(questions) < 100:
        prompt = seeds[(len(questions) - 1) % len(seeds)]
        questions.append(FactualBenchmarkQuestion(question=prompt, category="unit_conversion"))
    return questions


def _contains_expected(answer: str, expected: str) -> bool:
    normalized_answer = answer.lower().replace(",", ".")
    normalized_expected = expected.lower().replace(",", ".")
    if normalized_expected in normalized_answer:
        return True
    if "=" in normalized_expected:
        left, right = [part.strip() for part in normalized_expected.split("=", 1)]
        return left in normalized_answer and right in normalized_answer
    return False


def evaluate_answer(question: FactualBenchmarkQuestion, answer: str, elapsed_seconds: float) -> FactualBenchmarkResult:
    missing = tuple(fact for fact in question.expected_facts if not _contains_expected(answer, fact))
    forbidden = tuple(claim for claim in question.forbidden_claims if claim.lower().replace(",", ".") in answer.lower().replace(",", "."))
    accuracy = 1.0 if not question.expected_facts else (len(question.expected_facts) - len(missing)) / len(question.expected_facts)
    answer_chars = len(answer)
    unnecessary = answer_chars > 1800 and question.category in {"unit_conversion", "exact_fact"}
    return FactualBenchmarkResult(
        question=question.question,
        category=question.category,
        elapsed_seconds=round(elapsed_seconds, 4),
        factual_accuracy=round(max(0.0, accuracy), 4),
        hallucination_flag=bool(forbidden),
        unnecessary_information_flag=unnecessary,
        missing_expected_facts=missing,
        forbidden_claims_found=forbidden,
        answer_chars=answer_chars,
    )


def run_factual_benchmark(
    answer_fn: Callable[[str], str],
    questions: Iterable[FactualBenchmarkQuestion] | None = None,
    output_path: str | Path | None = None,
) -> dict:
    selected = list(questions or default_technical_questions())
    results: list[FactualBenchmarkResult] = []
    started = time.perf_counter()
    for item in selected:
        item_started = time.perf_counter()
        answer = answer_fn(item.question)
        results.append(evaluate_answer(item, answer, time.perf_counter() - item_started))
    summary = {
        "question_count": len(results),
        "average_factual_accuracy": round(sum(r.factual_accuracy for r in results) / max(1, len(results)), 4),
        "hallucination_rate": round(sum(1 for r in results if r.hallucination_flag) / max(1, len(results)), 4),
        "unnecessary_information_rate": round(sum(1 for r in results if r.unnecessary_information_flag) / max(1, len(results)), 4),
        "total_seconds": round(time.perf_counter() - started, 4),
        "results": [asdict(result) for result in results],
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
