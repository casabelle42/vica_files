#!/usr/bin/env python3

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime


# ======================================================================
# Utilities
# ======================================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def mean(values):
    values = [
        value for value in values
        if value is not None
    ]

    if not values:
        return None

    return sum(values) / len(values)


def safe_rate(numerator, denominator):
    if denominator == 0:
        return None

    return numerator / denominator


def fmt(value, digits=3):
    if value is None:
        return "N/A"

    return f"{value:.{digits}f}"


# ======================================================================
# Result discovery
# ======================================================================

def is_experiment_a_result(data):
    """
    Determine whether a JSON document is an Experiment A result file.
    """

    if not isinstance(data, dict):
        return False

    if data.get("experiment") != "A":
        return False

    if not isinstance(data.get("queries"), list):
        return False

    if not data.get("model"):
        return False

    if not data.get("video_id"):
        return False

    return True


def discover_result_files(results_dir):
    """
    Recursively discover valid Experiment A result JSON files.
    """

    results = []
    skipped = []

    for root, _, files in os.walk(results_dir):

        for filename in files:

            if not filename.lower().endswith(".json"):
                continue

            path = os.path.join(root, filename)

            try:
                data = load_json(path)

            except Exception as exc:
                skipped.append({
                    "path": path,
                    "reason": f"JSON load failed: {exc}"
                })
                continue

            if not is_experiment_a_result(data):
                skipped.append({
                    "path": path,
                    "reason": "not an Experiment A result"
                })
                continue

            results.append({
                "path": path,
                "data": data
            })

    return results, skipped


# ======================================================================
# Query extraction
# ======================================================================

def flatten_query_record(result_path, result, query):
    """
    Convert one query result into a flat record suitable for aggregation
    and CSV output.
    """

    metrics = query.get("metrics") or {}

    parsed_response = query.get("parsed_response")

    sufficient_evidence_identified = None
    evidence_interval_count = None

    if isinstance(parsed_response, dict):

        sufficient_evidence_identified = (
            parsed_response.get(
                "sufficient_evidence_identified"
            )
        )

        evidence = parsed_response.get("evidence")

        if isinstance(evidence, list):
            evidence_interval_count = len(evidence)

    return {
        "source_file": result_path,

        "experiment": result.get("experiment"),
        "model": result.get("model"),
        "model_display_name": result.get(
            "model_display_name",
            result.get("model")
        ),

        "video_id": result.get("video_id"),
        "video_file": result.get("video_file"),

        "sample_fps": (
            result.get("configuration", {})
            .get("sample_fps")
        ),

        "query_id": query.get("query_id"),
        "query": query.get("query"),
        "query_type": query.get("query_type"),

        "execution_success": bool(
            query.get("execution_success", False)
        ),

        "return_code": query.get("return_code"),

        "parse_success": bool(
            query.get("parse_success", False)
        ),

        "validation_success": bool(
            query.get("validation_success", False)
        ),

        "validation_error": query.get(
            "validation_error"
        ),

        "response_status": query.get(
            "response_status"
        ),

        "sufficient_evidence_identified":
            sufficient_evidence_identified,

        "evidence_interval_count":
            evidence_interval_count,

        "selected_duration_seconds":
            metrics.get(
                "selected_duration_seconds"
            ),

        "relevant_duration_seconds":
            metrics.get(
                "relevant_duration_seconds"
            ),

        "intersection_seconds":
            metrics.get(
                "intersection_seconds"
            ),

        "temporal_precision":
            metrics.get(
                "temporal_precision"
            ),

        "temporal_recall":
            metrics.get(
                "temporal_recall"
            ),

        "temporal_iou":
            metrics.get(
                "temporal_iou"
            ),

        "percentage_video_retained":
            metrics.get(
                "percentage_video_retained"
            ),

        "minimal_sufficient_duration_seconds":
            metrics.get(
                "minimal_sufficient_duration_seconds"
            ),

        "minimal_sufficient_intersection_seconds":
            metrics.get(
                "minimal_sufficient_intersection_seconds"
            ),

        "minimal_sufficient_coverage":
            metrics.get(
                "minimal_sufficient_coverage"
            ),

        "minimal_sufficient_fully_covered":
            metrics.get(
                "minimal_sufficient_fully_covered"
            ),

        "hard_negative_duration_seconds":
            metrics.get(
                "hard_negative_duration_seconds"
            ),

        "hard_negative_selected_seconds":
            metrics.get(
                "hard_negative_selected_seconds"
            ),

        "hard_negative_fp_rate":
            metrics.get(
                "hard_negative_fp_rate"
            ),

        "excluded_duration_seconds":
            metrics.get(
                "excluded_duration_seconds"
            ),

        "excluded_selected_seconds":
            metrics.get(
                "excluded_selected_seconds"
            ),

        "relevant_segments_found":
            metrics.get(
                "relevant_segments_found"
            ),

        "relevant_segments_total":
            metrics.get(
                "relevant_segments_total"
            ),

        "relevant_segment_recall":
            metrics.get(
                "relevant_segment_recall"
            ),

        "event_level_miss":
            metrics.get(
                "event_level_miss"
            ),
    }


# ======================================================================
# Aggregation
# ======================================================================

def aggregate_queries(records):
    """
    Aggregate query records directly.

    Metrics are calculated from query-level records rather than by
    averaging per-video summaries.
    """

    total_queries = len(records)

    execution_successes = sum(
        1 for r in records
        if r["execution_success"]
    )

    parse_successes = sum(
        1 for r in records
        if r["parse_success"]
    )

    validation_successes = sum(
        1 for r in records
        if r["validation_success"]
    )

    valid_responses = sum(
        1 for r in records
        if r["response_status"] == "valid"
    )

    sufficient_claimed = sum(
        1 for r in records
        if r["sufficient_evidence_identified"] is True
    )

    zero_evidence_outputs = sum(
        1 for r in records
        if (
            r["evidence_interval_count"] == 0
            or (
                r["sufficient_evidence_identified"] is False
                and r["evidence_interval_count"] is None
            )
        )
    )

    scored_records = [
        r for r in records
        if r["temporal_precision"] is not None
    ]

    event_records = [
        r for r in records
        if r["event_level_miss"] is not None
    ]

    event_level_misses = sum(
        1 for r in event_records
        if r["event_level_miss"] is True
    )

    minimal_records = [
        r for r in records
        if r["minimal_sufficient_coverage"]
        is not None
    ]

    minimal_fully_covered = sum(
        1 for r in minimal_records
        if r["minimal_sufficient_fully_covered"]
        is True
    )

    hard_negative_records = [
        r for r in records
        if r["hard_negative_fp_rate"]
        is not None
    ]

    excluded_records = [
        r for r in records
        if r["excluded_selected_seconds"]
        is not None
    ]

    return {
        "total_queries": total_queries,

        "execution_successes":
            execution_successes,

        "execution_success_rate":
            safe_rate(
                execution_successes,
                total_queries
            ),

        "parse_successes":
            parse_successes,

        "parse_success_rate":
            safe_rate(
                parse_successes,
                total_queries
            ),

        "validation_successes":
            validation_successes,

        "validation_success_rate":
            safe_rate(
                validation_successes,
                total_queries
            ),

        "valid_responses":
            valid_responses,

        "valid_response_rate":
            safe_rate(
                valid_responses,
                total_queries
            ),

        "sufficient_claimed":
            sufficient_claimed,

        "zero_evidence_outputs":
            zero_evidence_outputs,

        "scored_runs":
            len(scored_records),

        "event_level_misses":
            event_level_misses,

        "event_level_scored_queries":
            len(event_records),

        "event_level_miss_rate":
            safe_rate(
                event_level_misses,
                len(event_records)
            ),

        "mean_temporal_precision":
            mean([
                r["temporal_precision"]
                for r in scored_records
            ]),

        "mean_temporal_recall":
            mean([
                r["temporal_recall"]
                for r in scored_records
            ]),

        "mean_temporal_iou":
            mean([
                r["temporal_iou"]
                for r in scored_records
            ]),

        "mean_relevant_segment_recall":
            mean([
                r["relevant_segment_recall"]
                for r in scored_records
            ]),

        "mean_percentage_video_retained":
            mean([
                r["percentage_video_retained"]
                for r in scored_records
            ]),

        "minimal_sufficient_queries":
            len(minimal_records),

        "mean_minimal_sufficient_coverage":
            mean([
                r["minimal_sufficient_coverage"]
                for r in minimal_records
            ]),

        "minimal_sufficient_fully_covered":
            minimal_fully_covered,

        "minimal_sufficient_full_coverage_rate":
            safe_rate(
                minimal_fully_covered,
                len(minimal_records)
            ),

        "hard_negative_queries":
            len(hard_negative_records),

        "mean_hard_negative_fp_rate":
            mean([
                r["hard_negative_fp_rate"]
                for r in hard_negative_records
            ]),

        "mean_hard_negative_selected_seconds":
            mean([
                r["hard_negative_selected_seconds"]
                for r in hard_negative_records
            ]),

        "mean_excluded_selected_seconds":
            mean([
                r["excluded_selected_seconds"]
                for r in excluded_records
            ]),
    }


def aggregate_by_video(records):
    """
    Produce one aggregate record for every video.
    """

    groups = defaultdict(list)

    for record in records:
        groups[record["video_id"]].append(
            record
        )

    output = {}

    for video_id in sorted(groups):

        video_records = groups[video_id]

        output[video_id] = {
            "video_id": video_id,
            "video_file":
                video_records[0]["video_file"],
            "total_queries":
                len(video_records),
            "summary":
                aggregate_queries(video_records)
        }

    return output


def aggregate_by_query_type(records):
    """
    Useful for comparing direct-event, temporal-reasoning,
    state-context, etc. behavior.
    """

    groups = defaultdict(list)

    for record in records:

        query_type = (
            record["query_type"]
            or "unknown"
        )

        groups[query_type].append(record)

    output = {}

    for query_type in sorted(groups):

        output[query_type] = {
            "total_queries":
                len(groups[query_type]),

            "summary":
                aggregate_queries(
                    groups[query_type]
                )
        }

    return output


# ======================================================================
# CSV output
# ======================================================================

def write_query_csv(path, records):

    if not records:
        return

    fieldnames = list(
        records[0].keys()
    )

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(records)


def write_video_csv(path, compiled_models):

    rows = []

    for model, model_data in compiled_models.items():

        for video_id, video_data in (
            model_data["per_video"].items()
        ):

            summary = video_data["summary"]

            rows.append({
                "model": model,
                "model_display_name":
                    model_data[
                        "model_display_name"
                    ],

                "video_id": video_id,
                "video_file":
                    video_data["video_file"],

                "total_queries":
                    summary["total_queries"],

                "execution_success_rate":
                    summary[
                        "execution_success_rate"
                    ],

                "parse_success_rate":
                    summary[
                        "parse_success_rate"
                    ],

                "validation_success_rate":
                    summary[
                        "validation_success_rate"
                    ],

                "event_level_miss_rate":
                    summary[
                        "event_level_miss_rate"
                    ],

                "mean_temporal_precision":
                    summary[
                        "mean_temporal_precision"
                    ],

                "mean_temporal_recall":
                    summary[
                        "mean_temporal_recall"
                    ],

                "mean_temporal_iou":
                    summary[
                        "mean_temporal_iou"
                    ],

                "mean_relevant_segment_recall":
                    summary[
                        "mean_relevant_segment_recall"
                    ],

                "mean_percentage_video_retained":
                    summary[
                        "mean_percentage_video_retained"
                    ],

                "mean_minimal_sufficient_coverage":
                    summary[
                        "mean_minimal_sufficient_coverage"
                    ],

                "minimal_sufficient_full_coverage_rate":
                    summary[
                        "minimal_sufficient_full_coverage_rate"
                    ],

                "mean_hard_negative_fp_rate":
                    summary[
                        "mean_hard_negative_fp_rate"
                    ],

                "mean_excluded_selected_seconds":
                    summary[
                        "mean_excluded_selected_seconds"
                    ],
            })

    if not rows:
        return

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys())
        )

        writer.writeheader()
        writer.writerows(rows)


def write_model_csv(path, compiled_models):

    rows = []

    for model, model_data in compiled_models.items():

        summary = model_data["summary"]

        rows.append({
            "model": model,
            "model_display_name":
                model_data[
                    "model_display_name"
                ],

            "videos":
                model_data["video_count"],

            "total_queries":
                summary["total_queries"],

            "execution_success_rate":
                summary[
                    "execution_success_rate"
                ],

            "parse_success_rate":
                summary[
                    "parse_success_rate"
                ],

            "validation_success_rate":
                summary[
                    "validation_success_rate"
                ],

            "event_level_miss_rate":
                summary[
                    "event_level_miss_rate"
                ],

            "mean_temporal_precision":
                summary[
                    "mean_temporal_precision"
                ],

            "mean_temporal_recall":
                summary[
                    "mean_temporal_recall"
                ],

            "mean_temporal_iou":
                summary[
                    "mean_temporal_iou"
                ],

            "mean_relevant_segment_recall":
                summary[
                    "mean_relevant_segment_recall"
                ],

            "mean_percentage_video_retained":
                summary[
                    "mean_percentage_video_retained"
                ],

            "mean_minimal_sufficient_coverage":
                summary[
                    "mean_minimal_sufficient_coverage"
                ],

            "minimal_sufficient_full_coverage_rate":
                summary[
                    "minimal_sufficient_full_coverage_rate"
                ],

            "hard_negative_queries":
                summary[
                    "hard_negative_queries"
                ],

            "mean_hard_negative_fp_rate":
                summary[
                    "mean_hard_negative_fp_rate"
                ],

            "mean_excluded_selected_seconds":
                summary[
                    "mean_excluded_selected_seconds"
                ],
        })

    if not rows:
        return

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys())
        )

        writer.writeheader()
        writer.writerows(rows)


# ======================================================================
# Terminal reporting
# ======================================================================

def print_model_summary(model_data):

    summary = model_data["summary"]

    print()
    print("=" * 70)
    print(
        f"Experiment A — "
        f"{model_data['model_display_name']}"
    )
    print("=" * 70)

    print(
        f"Videos:                       "
        f"{model_data['video_count']}"
    )

    print(
        f"Queries:                      "
        f"{summary['total_queries']}"
    )

    print()

    print(
        f"Execution success:            "
        f"{summary['execution_successes']}/"
        f"{summary['total_queries']} "
        f"({fmt(summary['execution_success_rate'])})"
    )

    print(
        f"Parse success:                "
        f"{summary['parse_successes']}/"
        f"{summary['total_queries']} "
        f"({fmt(summary['parse_success_rate'])})"
    )

    print(
        f"Validation success:           "
        f"{summary['validation_successes']}/"
        f"{summary['total_queries']} "
        f"({fmt(summary['validation_success_rate'])})"
    )

    print(
        f"Valid responses:              "
        f"{summary['valid_responses']}/"
        f"{summary['total_queries']} "
        f"({fmt(summary['valid_response_rate'])})"
    )

    print(
        f"Event-level misses:           "
        f"{summary['event_level_misses']}/"
        f"{summary['event_level_scored_queries']} "
        f"({fmt(summary['event_level_miss_rate'])})"
    )

    print()

    print(
        f"Mean precision:               "
        f"{fmt(summary['mean_temporal_precision'])}"
    )

    print(
        f"Mean recall:                  "
        f"{fmt(summary['mean_temporal_recall'])}"
    )

    print(
        f"Mean IoU:                     "
        f"{fmt(summary['mean_temporal_iou'])}"
    )

    print(
        f"Mean segment recall:          "
        f"{fmt(summary['mean_relevant_segment_recall'])}"
    )

    retained = (
        summary[
            "mean_percentage_video_retained"
        ]
    )

    if retained is None:
        retained_text = "N/A"
    else:
        retained_text = f"{retained:.1f}%"

    print(
        f"Mean video retained:          "
        f"{retained_text}"
    )

    print(
        f"Mean minimal coverage:        "
        f"{fmt(summary['mean_minimal_sufficient_coverage'])}"
    )

    print(
        f"Minimal full coverage:        "
        f"{summary['minimal_sufficient_fully_covered']}/"
        f"{summary['minimal_sufficient_queries']} "
        f"({fmt(summary['minimal_sufficient_full_coverage_rate'])})"
    )

    print(
        f"Hard-negative queries:        "
        f"{summary['hard_negative_queries']}"
    )

    print(
        f"Mean hard-negative FP rate:   "
        f"{fmt(summary['mean_hard_negative_fp_rate'])}"
    )

    print(
        f"Mean excluded selected:       "
        f"{fmt(summary['mean_excluded_selected_seconds'])}s"
    )

    print()
    print("Per-video results")
    print("-" * 70)

    print(
        f"{'Video':<14}"
        f"{'Prec':>8}"
        f"{'Recall':>8}"
        f"{'IoU':>8}"
        f"{'SegRec':>8}"
        f"{'Retain':>9}"
        f"{'Miss':>8}"
    )

    for video_id, video_data in (
        model_data["per_video"].items()
    ):

        s = video_data["summary"]

        retained = (
            s["mean_percentage_video_retained"]
        )

        retained_text = (
            "N/A"
            if retained is None
            else f"{retained:.1f}%"
        )

        miss_rate = s["event_level_miss_rate"]

        miss_text = (
            "N/A"
            if miss_rate is None
            else f"{miss_rate:.3f}"
        )

        print(
            f"{video_id:<14}"
            f"{fmt(s['mean_temporal_precision']):>8}"
            f"{fmt(s['mean_temporal_recall']):>8}"
            f"{fmt(s['mean_temporal_iou']):>8}"
            f"{fmt(s['mean_relevant_segment_recall']):>8}"
            f"{retained_text:>9}"
            f"{miss_text:>8}"
        )


def print_comparison(compiled_models):

    if len(compiled_models) < 2:
        return

    print()
    print("=" * 70)
    print("Experiment A — Model Comparison")
    print("=" * 70)

    headers = [
        "Metric"
    ]

    model_keys = list(
        compiled_models.keys()
    )

    for model in model_keys:
        headers.append(
            compiled_models[model][
                "model_display_name"
            ]
        )

    print(
        f"{headers[0]:<32}",
        end=""
    )

    for header in headers[1:]:
        print(
            f"{header:>18}",
            end=""
        )

    print()

    print("-" * (
        32 + 18 * len(model_keys)
    ))

    metrics = [
        (
            "Precision",
            "mean_temporal_precision"
        ),
        (
            "Recall",
            "mean_temporal_recall"
        ),
        (
            "Temporal IoU",
            "mean_temporal_iou"
        ),
        (
            "Segment recall",
            "mean_relevant_segment_recall"
        ),
        (
            "Video retained (%)",
            "mean_percentage_video_retained"
        ),
        (
            "Minimal coverage",
            "mean_minimal_sufficient_coverage"
        ),
        (
            "Minimal full coverage",
            "minimal_sufficient_full_coverage_rate"
        ),
        (
            "Event miss rate",
            "event_level_miss_rate"
        ),
        (
            "Hard-negative FP rate",
            "mean_hard_negative_fp_rate"
        ),
        (
            "Validation success",
            "validation_success_rate"
        ),
    ]

    for label, key in metrics:

        print(
            f"{label:<32}",
            end=""
        )

        for model in model_keys:

            value = (
                compiled_models[model]
                ["summary"]
                .get(key)
            )

            print(
                f"{fmt(value):>18}",
                end=""
            )

        print()


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Compile Experiment A results "
            "across videos and models."
        )
    )

    parser.add_argument(
        "--results-dir",
        required=True,
        help=(
            "Directory containing Experiment A "
            "result JSON files. Subdirectories "
            "are searched recursively."
        )
    )

    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for compiled output. "
            "Defaults to <results-dir>/compiled."
        )
    )

    args = parser.parse_args()

    results_dir = os.path.abspath(
        args.results_dir
    )

    output_dir = (
        os.path.abspath(args.output_dir)
        if args.output_dir
        else os.path.join(
            results_dir,
            "compiled"
        )
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    results, skipped = (
        discover_result_files(
            results_dir
        )
    )

    if not results:
        raise RuntimeError(
            "No Experiment A result files "
            f"found in {results_dir}"
        )

    # --------------------------------------------------------------
    # Group query records by model
    # --------------------------------------------------------------

    model_records = defaultdict(list)

    model_display_names = {}

    model_video_ids = defaultdict(set)

    source_files = defaultdict(list)

    for item in results:

        path = item["path"]
        result = item["data"]

        model = result["model"]

        model_display_names[model] = (
            result.get(
                "model_display_name",
                model
            )
        )

        model_video_ids[model].add(
            result["video_id"]
        )

        source_files[model].append(path)

        for query in result["queries"]:

            record = flatten_query_record(
                path,
                result,
                query
            )

            model_records[model].append(
                record
            )

    # --------------------------------------------------------------
    # Compile each model
    # --------------------------------------------------------------

    compiled_models = {}

    all_query_records = []

    for model in sorted(model_records):

        records = model_records[model]

        all_query_records.extend(records)

        compiled_models[model] = {
            "model": model,

            "model_display_name":
                model_display_names[model],

            "video_count":
                len(model_video_ids[model]),

            "video_ids":
                sorted(
                    model_video_ids[model]
                ),

            "source_files":
                sorted(
                    source_files[model]
                ),

            "summary":
                aggregate_queries(records),

            "per_video":
                aggregate_by_video(records),

            "per_query_type":
                aggregate_by_query_type(
                    records
                ),
        }

    # --------------------------------------------------------------
    # Build compiled document
    # --------------------------------------------------------------

    compiled = {
        "experiment": "A",

        "compiled_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "results_directory":
            results_dir,

        "result_files_found":
            len(results),

        "skipped_json_files":
            skipped,

        "models":
            compiled_models,
    }

    # --------------------------------------------------------------
    # Save outputs
    # --------------------------------------------------------------

    compiled_json = os.path.join(
        output_dir,
        "experiment_a_compiled.json"
    )

    query_csv = os.path.join(
        output_dir,
        "experiment_a_query_results.csv"
    )

    video_csv = os.path.join(
        output_dir,
        "experiment_a_video_results.csv"
    )

    model_csv = os.path.join(
        output_dir,
        "experiment_a_model_results.csv"
    )

    save_json(
        compiled_json,
        compiled
    )

    write_query_csv(
        query_csv,
        all_query_records
    )

    write_video_csv(
        video_csv,
        compiled_models
    )

    write_model_csv(
        model_csv,
        compiled_models
    )

    # --------------------------------------------------------------
    # Report
    # --------------------------------------------------------------

    print()
    print(
        f"Experiment A result files found: "
        f"{len(results)}"
    )

    if skipped:
        print(
            f"Other JSON files skipped: "
            f"{len(skipped)}"
        )

    for model in sorted(
        compiled_models
    ):
        print_model_summary(
            compiled_models[model]
        )

    print_comparison(
        compiled_models
    )

    print()
    print("=" * 70)
    print("Compiled outputs")
    print("=" * 70)

    print(compiled_json)
    print(query_csv)
    print(video_csv)
    print(model_csv)


if __name__ == "__main__":
    main()