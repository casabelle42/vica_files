#!/usr/bin/env python3
"""LAS-VICA shared B/C scoring orchestrator (host-side).

Runs completed Experiment B or C results through the existing shared score_response
scorer using one persistent Qwen3 Docker session. Supports many result files,
resume/checkpoints, and aggregation. Experiment A/C *inference* orchestration
is intentionally not implemented until their interfaces are finalized.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

# The installed shared scorer lives alongside this script in evaluation/.
from score_response import (score_candidate,
                            load_json, load_text, PROJECT_ROOT,
                            DEFAULT_SCORER_PROMPT)

from api_scorer import OpenAIScorer, BudgetExceeded

B_CONDITIONS = ("ground_truth_evidence", "model_selected_evidence")
C_CONDITIONS = ("isolated_frame", "sparse_frames", "short_sequence", "full_relevant", "full_video")


def atomic_save(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
    os.replace(temporary, path)


def result_paths(specs):
    paths = []
    for spec in specs:
        if os.path.isdir(spec):
            paths.extend(glob.glob(os.path.join(spec, "**", "*.json"), recursive=True))
        else:
            matches = glob.glob(spec, recursive=True)
            if not matches:
                raise FileNotFoundError(spec)
            paths.extend(matches)
    return sorted(set(os.path.abspath(p) for p in paths))


def annotation_path(video_id, annotation_dir, explicit):
    if explicit:
        return explicit
    return os.path.join(annotation_dir, video_id + ".json")


def jobs_from_result(result, experiment_type):
    for query in result.get("queries", []):
        qid = query.get("query_id")
        for name in (B_CONDITIONS if experiment_type == "B" else C_CONDITIONS):
            condition = query.get("conditions", {}).get(name, {})
            parsed = condition.get("parsed_response")
            answer = parsed.get("answer") if isinstance(parsed, dict) else None
            yield qid, name, answer if condition.get("validation_success") else None


def summarize(entries):
    counts = {"total": len(entries), "valid": 0, "invalid": 0,
              "skipped": 0, "error": 0}
    by_condition = {}
    metrics = {}
    for entry in entries:
        status = entry.get("status", "error")
        counts[status] = counts.get(status, 0) + 1
        condition = entry.get("condition", "unknown")
        bucket = by_condition.setdefault(condition, {"total": 0, "valid": 0,
                                                       "invalid": 0, "skipped": 0, "error": 0})
        bucket["total"] += 1
        bucket[status] = bucket.get(status, 0) + 1
        if status == "valid":
            for key, value in (entry.get("metrics") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics.setdefault(condition, {}).setdefault(key, []).append(value)
    means = {condition: {key: sum(vals) / len(vals) for key, vals in fields.items()}
             for condition, fields in metrics.items()}
    return {"counts": counts, "by_condition": by_condition,
            "mean_metrics_by_condition_valid_only": means}


def main():
    parser = argparse.ArgumentParser(description="Batch score LAS-VICA Experiment B or C results with persistent shared B/C scorer")
    parser.add_argument("--experiment", choices=["B", "C"], default="B",
                        help="Experiment type to score (default: B)")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--experiment-b", nargs="+",
                              help="Experiment B inference JSON files, directories, or globs")
    source_group.add_argument("--experiment-c", nargs="+",
                              help="Experiment C inference JSON files, directories, or globs")
    parser.add_argument("--model", help="Score only inference results whose JSON model field matches this value")
    parser.add_argument("--annotation", help="Annotation file; use only for one video")
    parser.add_argument("--annotation-dir", default="videos/counterfactual_vids/annotations")
    parser.add_argument("--scorer-prompt", default=DEFAULT_SCORER_PROMPT)
    parser.add_argument("--output", help="Output JSON file for a single experiment input")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--summary-output", default=None)
    parser.add_argument("--project-root", default=PROJECT_ROOT)
    parser.add_argument("--api-model", default="gpt-5-mini")
    parser.add_argument("--max-usd", type=float, default=50.0)
    parser.add_argument("--input-usd-per-million", type=float, default=0.25)
    parser.add_argument("--output-usd-per-million", type=float, default=2.0)
    parser.add_argument("--usage-log", default="results/scoring/api_usage.jsonl")
    parser.add_argument("--image", default="qwen-scorer")
    parser.add_argument("--inference-script", default="/workspace/models/qwen3/qwen3_infer.py")
    parser.add_argument("--max-new-tokens", type=int, default=3000)
    parser.add_argument("--retry-failed", action="store_true", help="Retry previously saved invalid/error results")
    parser.add_argument("--force", action="store_true", help="Rescore all answers")
    args = parser.parse_args()

    if args.experiment == "B" and not args.experiment_b:
        parser.error("--experiment B requires --experiment-b")
    if args.experiment == "C" and not args.experiment_c:
        parser.error("--experiment C requires --experiment-c")
    specs = args.experiment_b if args.experiment == "B" else args.experiment_c
    if args.output_dir is None:
        args.output_dir = f"results/scoring/api/{args.api_model}/experiment_{args.experiment.lower()}"
    if args.summary_output is None:
        suffix = f"_{args.model}" if args.model else ""
        suffix += f"_{args.api_model}"
        args.summary_output = f"results/scoring/api/experiment_{args.experiment.lower()}{suffix}_summary.json"
    inputs = result_paths(specs)
    # Never ingest scored outputs, including when scanning experiment directories.
    selected = []
    for path in inputs:
        if os.path.basename(path).startswith("scored_"):
            continue
        try:
            item = load_json(path)
        except (ValueError, OSError):
            continue
        if isinstance(item, dict) and item.get("experiment") == args.experiment and isinstance(item.get("queries"), list):
            if args.model is None or item.get("model") == args.model:
                selected.append((path, item))
        elif len(specs) == 1 and os.path.isfile(specs[0]):
            parser.error(f"Input file is not an Experiment {args.experiment} inference results JSON")
    if not selected:
        parser.error(f"No Experiment {args.experiment} inference results found" + (f" for model {args.model!r}" if args.model else ""))
    if args.annotation and len(selected) != 1:
        parser.error("--annotation can only be used with one input file")
    if args.output and len(selected) != 1:
        parser.error("--output can only be used with one input file")

    frozen_prompt = load_text(args.scorer_prompt)
    prompt_sha256 = hashlib.sha256(frozen_prompt.encode("utf-8")).hexdigest()
    plans = []
    for source, experiment in selected:
        video_id = experiment.get("video_id")
        model = experiment.get("model")
        if not video_id or not model:
            raise ValueError(f"Missing video_id/model: {source}")
        annotation_file = annotation_path(video_id, args.annotation_dir, args.annotation)
        annotation = load_json(annotation_file)
        if annotation.get("video_id") != video_id:
            raise ValueError(f"Annotation mismatch: {annotation_file} vs {source}")
        output_file = args.output or os.path.join(args.output_dir, "scored_" + os.path.basename(source))
        if os.path.abspath(output_file) == source:
            raise ValueError("Output would overwrite source inference results")
        if os.path.isfile(output_file) and not args.force:
            saved = load_json(output_file)
            if (saved.get("experiment") != args.experiment or saved.get("source_results", saved.get("experiment_b_source")) != source
                or saved.get("grader_model") != args.api_model):
                raise ValueError(f"Existing output belongs to a different experiment/source: {output_file}")
            if saved.get("scorer_prompt_sha256") != prompt_sha256:
                print(f"Scorer prompt changed (or old hash missing): rescoring {video_id} with new prompt", flush=True)
                saved["scores"] = []
        else:
            saved = {"experiment": args.experiment, "video_id": video_id, "model": model,
                     "grader_backend": "openai_api", "grader_model": args.api_model,
                     "source_results": source, "annotation_source": annotation_file,
                     "scorer_prompt": args.scorer_prompt, "scores": [], "summary": {}}
        saved["scorer_prompt_sha256"] = prompt_sha256
        if args.experiment == "B":
            saved["experiment_b_source"] = source
        else:
            saved["experiment_c_source"] = source
        jobs = list(jobs_from_result(experiment, args.experiment))
        plans.append((annotation, output_file, saved, jobs))

    pending = 0
    for _, _, saved, jobs in plans:
        previous = {(e.get("query_id"), e.get("condition")): e for e in saved["scores"]}
        for qid, condition, answer in jobs:
            old = previous.get((qid, condition))
            if (args.force or old is None or (args.retry_failed and old.get("status") in ("invalid", "error"))
                    or (old is not None and old.get("candidate_answer") != answer)):
                pending += 1
    print(f"Found {len(plans)} result file(s), {pending} scoring job(s) to process", flush=True)

    def process(session):
        for annotation, output_file, saved, jobs in plans:
            entries = {(e.get("query_id"), e.get("condition")): e for e in saved["scores"]}
            for qid, condition, answer in jobs:
                key = (qid, condition)
                old = entries.get(key)
                if old and not args.force and old.get("candidate_answer") == answer and not (args.retry_failed and old.get("status") in ("invalid", "error")):
                    continue
                if not isinstance(answer, str) or not answer.strip():
                    record = {"query_id": qid, "condition": condition, "candidate_answer": answer,
                              "status": "skipped", "reason": "No valid parsed candidate answer"}
                else:
                    try:
                        record = score_candidate(annotation, qid, answer, frozen_prompt, session)
                        record["condition"] = condition
                        record["status"] = "valid" if record["validation_success"] else "invalid"
                    except BudgetExceeded:
                        raise
                    except Exception as exc:
                        record = {"query_id": qid, "condition": condition, "candidate_answer": answer,
                                  "status": "error", "error": f"{type(exc).__name__}: {exc}"}
                        entries[key] = record
                        saved["scores"] = list(entries.values())
                        saved["summary"] = summarize(saved["scores"])
                        atomic_save(output_file, saved)
                        raise
                entries[key] = record
                saved["scores"] = list(entries.values())
                saved["summary"] = summarize(saved["scores"])
                atomic_save(output_file, saved)
                print(f"{saved['video_id']} {saved['model']} {qid} {condition}: {record['status']}", flush=True)
            saved["scores"] = list(entries.values())
            saved["summary"] = summarize(saved["scores"])
            atomic_save(output_file, saved)
            print(f"Saved {output_file}", flush=True)

    if pending:
        with OpenAIScorer(model=args.api_model, max_output_tokens=args.max_new_tokens,
                              max_usd=args.max_usd, input_usd_per_m=args.input_usd_per_million,
                              output_usd_per_m=args.output_usd_per_million,
                              usage_log=args.usage_log) as session:
            process(session)
    else:
        process(None)
    overview = {"experiment": args.experiment, "model_filter": args.model, "grader_model": args.api_model, "generated_at": datetime.now(timezone.utc).isoformat(),
                "files": [{"video_id": saved["video_id"], "model": saved["model"],
                           "output": output_file, "summary": saved["summary"]}
                          for _, output_file, saved, _ in plans]}
    atomic_save(args.summary_output, overview)
    print(f"Saved summary: {args.summary_output}", flush=True)


if __name__ == "__main__":
    main()
