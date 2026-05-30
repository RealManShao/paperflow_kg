import os
import json
import time
import argparse

from dotenv import load_dotenv

from llm_qa import GraphRAG


load_dotenv()


def load_cases(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    questions = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f.readlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- "):
                line = line[2:].strip()
            if line:
                questions.append(line)

    # De-duplicate while preserving order
    seen = set()
    unique = []
    for q in questions:
        if q not in seen:
            unique.append(q)
            seen.add(q)
    return unique


def main():
    parser = argparse.ArgumentParser(description="Evaluate baseline vs augmented GraphRAG on a small case set")
    parser.add_argument("--cases", type=str, default="results/cases.md")
    parser.add_argument("--out", type=str, default="results/metrics.json")
    args = parser.parse_args()

    questions = load_cases(args.cases)
    if not questions:
        raise SystemExit(f"No questions found in {args.cases}")

    rag = GraphRAG()

    rows = []
    baseline_ok = 0
    augmented_ok = 0
    augmented_query_ok = 0

    for q in questions:
        row = {"question": q}

        t0 = time.time()
        try:
            baseline = rag.ask_baseline(q)
            row["baseline_answer"] = baseline.get("answer")
            row["baseline_error"] = None
            baseline_ok += 1
        except Exception as e:
            row["baseline_answer"] = None
            row["baseline_error"] = str(e)
        row["baseline_latency_s"] = round(time.time() - t0, 3)

        t1 = time.time()
        try:
            augmented = rag.ask_augmented(q)
            row["augmented_answer"] = augmented.get("answer")
            row["augmented_cypher"] = augmented.get("cypher")
            row["augmented_results"] = augmented.get("results")
            row["augmented_error"] = augmented.get("error")
            augmented_ok += 1
            if not augmented.get("error"):
                augmented_query_ok += 1
        except Exception as e:
            row["augmented_answer"] = None
            row["augmented_cypher"] = None
            row["augmented_results"] = None
            row["augmented_error"] = str(e)
        row["augmented_latency_s"] = round(time.time() - t1, 3)

        rows.append(row)

    metrics = {
        "num_cases": len(questions),
        "baseline_success": baseline_ok,
        "augmented_success": augmented_ok,
        "augmented_query_success": augmented_query_ok,
        "baseline_success_rate": round(baseline_ok / len(questions), 3),
        "augmented_success_rate": round(augmented_ok / len(questions), 3),
        "augmented_query_success_rate": round(augmented_query_ok / len(questions), 3),
        "rows": rows,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(json.dumps({k: metrics[k] for k in metrics if k != "rows"}, ensure_ascii=False, indent=2))
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
