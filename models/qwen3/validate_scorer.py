#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
from collections import Counter, defaultdict

PROJECT_ROOT = "/home/las_edge_account/LAS-VICA"
DEFAULT_VALIDATION = os.path.join(PROJECT_ROOT, "models", "qwen3", "scorer_validation.json")
DEFAULT_PROMPT = os.path.join(PROJECT_ROOT, "prompts", "BandCprompt_scorer.txt")
DEFAULT_INFER_SCRIPT = "/workspace/models/qwen3/qwen3_infer.py"
DEFAULT_CONTAINER = "qwen3-scorer"

LABELS = ["SUPPORTED", "NOT_MENTIONED", "CONTRADICTED"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def strip_fence(text):
    text = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S)
    return m.group(1).strip() if m else text


def extract_response(stdout):
    patterns = [
        r"=== Qwen3 Response ===\s*(.*?)\s*=== End Response ===",
        r"=== Qwen3-14B Response ===\s*(.*?)\s*=== End Response ===",
    ]
    for pattern in patterns:
        m = re.search(pattern, stdout, flags=re.S)
        if m:
            return m.group(1).strip()
    return stdout.strip()


def build_case_prompt(base_prompt, case):
    # This mirrors the information supplied to the B/C judge:
    # query, reference, semantic claim components, temporal relations,
    # and candidate answer.
    payload = {
        "analyst_query": case["query"],
        "reference_answer": case["reference_answer"],
        "required_claims": case.get("required_claims", []),
        "temporal_relations": case.get("temporal_relations", []),
        "candidate_answer": case["candidate_answer"],
    }

    output_contract = {
        "required_claims": [
            {
                "claim_id": claim["claim_id"],
                "components": {
                    name: "<SUPPORTED|CONTRADICTED|NOT_MENTIONED>"
                    for name in claim.get("components", {})
                },
            }
            for claim in case.get("required_claims", [])
        ],
        "temporal_relations": [
            {
                "relation_id": relation["relation_id"],
                "classification": "<SUPPORTED|CONTRADICTED|NOT_MENTIONED>",
            }
            for relation in case.get("temporal_relations", [])
        ],
        "candidate_claims": [
            {
                "text": "<candidate factual claim>",
                "classification": "<SUPPORTED|UNSUPPORTED>",
            }
        ],
    }

    return (
        base_prompt.rstrip()
        + "\n\nINPUT\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n\nREQUIRED OUTPUT SHAPE\n"
        + json.dumps(output_contract, indent=2, ensure_ascii=False)
    )


def run_qwen(question, container, infer_script):
    command = [
        "docker", "run", "--rm",
        "--runtime", "nvidia",
        "--ipc=host",
        "--ulimit", "memlock=-1",
        "--ulimit", "stack=67108864",
        "-v", f"{PROJECT_ROOT}:/workspace",
        "--entrypoint", "python3",
        container,
        infer_script,
        "--prompt", question,
    ]

    completed = subprocess.run(command, capture_output=True, text=True)

    if completed.returncode != 0:
        return {
            "success": False,
            "error": completed.stderr.strip(),
            "raw": None,
            "parsed": None,
        }

    raw = extract_response(completed.stdout)

    try:
        parsed = json.loads(strip_fence(raw))
    except json.JSONDecodeError as exc:
        return {
            "success": False,
            "error": f"Invalid scorer JSON: {exc}",
            "raw": raw,
            "parsed": None,
        }

    return {"success": True, "error": None, "raw": raw, "parsed": parsed}


def index_claims(items):
    return {x.get("claim_id"): x for x in items if isinstance(x, dict)}


def index_relations(items):
    return {x.get("relation_id"): x for x in items if isinstance(x, dict)}


def compare_case(case, prediction):
    gold = case["expected"]
    mismatches = []
    observations = []

    gold_claims = index_claims(gold.get("required_claims", []))
    pred_claims = index_claims(prediction.get("required_claims", []))

    for claim_id, gold_claim in gold_claims.items():
        pred_claim = pred_claims.get(claim_id)
        if pred_claim is None:
            for component, expected in gold_claim.get("components", {}).items():
                observations.append(("component", component, expected, "MISSING"))
                mismatches.append(
                    f"{claim_id}.{component}: expected {expected}, got MISSING"
                )
            continue

        pred_components = pred_claim.get("components", {})
        for component, expected in gold_claim.get("components", {}).items():
            actual = pred_components.get(component, "MISSING")
            observations.append(("component", component, expected, actual))
            if actual != expected:
                mismatches.append(
                    f"{claim_id}.{component}: expected {expected}, got {actual}"
                )

    gold_rel = index_relations(gold.get("temporal_relations", []))
    pred_rel = index_relations(prediction.get("temporal_relations", []))

    for relation_id, gold_item in gold_rel.items():
        expected = gold_item["classification"]
        actual = pred_rel.get(relation_id, {}).get("classification", "MISSING")
        observations.append(("temporal", "temporal_relation", expected, actual))
        if actual != expected:
            mismatches.append(
                f"{relation_id}: expected {expected}, got {actual}"
            )

    return observations, mismatches


def print_confusion(confusion):
    cols = LABELS + ["MISSING"]
    print("\nComponent/temporal confusion matrix")
    print("Expected".ljust(18) + "".join(c[:7].rjust(10) for c in cols))
    for expected in LABELS:
        row = expected.ljust(18)
        for actual in cols:
            row += str(confusion[(expected, actual)]).rjust(10)
        print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Validate the LAS-VICA Qwen3 B/C scorer against controlled gold cases."
    )
    parser.add_argument("--validation", default=DEFAULT_VALIDATION)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--infer-script", default=DEFAULT_INFER_SCRIPT)
    parser.add_argument("--case-id", default=None, help="Run only one validation case.")
    parser.add_argument("--save-results", default=None)
    args = parser.parse_args()

    validation = load_json(args.validation)
    base_prompt = load_text(args.prompt)

    cases = validation["cases"]
    if args.case_id:
        cases = [c for c in cases if c["case_id"] == args.case_id]
        if not cases:
            raise ValueError(f"Unknown case: {args.case_id}")

    confusion = Counter()
    component_by_name = defaultdict(lambda: [0, 0])
    category_stats = defaultdict(lambda: [0, 0])
    all_results = []
    total_observations = 0
    correct_observations = 0
    execution_failures = 0

    for i, case in enumerate(cases, 1):
        print("\n" + "=" * 70)
        print(f"{i}/{len(cases)}  {case['case_id']}  [{case['category']}]")
        print("=" * 70)

        prompt = build_case_prompt(base_prompt, case)
        run = run_qwen(prompt, args.container, args.infer_script)

        record = {
            "case_id": case["case_id"],
            "category": case["category"],
            "success": run["success"],
            "prediction": run["parsed"],
            "error": run["error"],
            "mismatches": [],
        }

        if not run["success"]:
            execution_failures += 1
            print("FAILED:", run["error"])
            all_results.append(record)
            continue

        observations, mismatches = compare_case(case, run["parsed"])
        record["mismatches"] = mismatches
        all_results.append(record)

        case_correct = 0
        for kind, name, expected, actual in observations:
            total_observations += 1
            if expected in LABELS:
                confusion[(expected, actual)] += 1

            is_correct = expected == actual
            if is_correct:
                correct_observations += 1
                case_correct += 1

            component_by_name[name][1] += 1
            if is_correct:
                component_by_name[name][0] += 1

        category_stats[case["category"]][1] += len(observations)
        category_stats[case["category"]][0] += case_correct

        if mismatches:
            print("MISMATCH")
            for m in mismatches:
                print(" -", m)
        else:
            print("PASS")

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Cases attempted:       {len(cases)}")
    print(f"Execution failures:    {execution_failures}")
    print(f"Gold judgments:        {total_observations}")
    accuracy = correct_observations / total_observations if total_observations else 0.0
    print(f"Overall accuracy:      {accuracy:.3f} ({correct_observations}/{total_observations})")

    for label in LABELS:
        denom = sum(confusion[(label, x)] for x in LABELS + ["MISSING"])
        num = confusion[(label, label)]
        acc = num / denom if denom else 0.0
        print(f"{label + ' accuracy:':22s}{acc:.3f} ({num}/{denom})")

    print("\nAccuracy by semantic component")
    for name in sorted(component_by_name):
        num, denom = component_by_name[name]
        print(f"{name + ':':22s}{num/denom if denom else 0.0:.3f} ({num}/{denom})")

    print("\nAccuracy by validation category")
    for category in sorted(category_stats):
        num, denom = category_stats[category]
        print(f"{category + ':':28s}{num/denom if denom else 0.0:.3f} ({num}/{denom})")

    print_confusion(confusion)

    if args.save_results:
        output = {
            "validation_name": validation.get("name"),
            "summary": {
                "cases_attempted": len(cases),
                "execution_failures": execution_failures,
                "gold_judgments": total_observations,
                "correct_judgments": correct_observations,
                "overall_accuracy": accuracy,
            },
            "results": all_results,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.save_results)), exist_ok=True)
        with open(args.save_results, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nDetailed results saved to: {args.save_results}")


if __name__ == "__main__":
    main()
