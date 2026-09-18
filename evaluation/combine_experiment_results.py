#!/usr/bin/env python3

import argparse
import json
import os
from statistics import mean


CONDITION_ORDER = [
    "isolated_frame",
    "sparse_frames",
    "short_sequence",
    "full_relevant",
    "full_video",
]

CONDITION_LABELS = {
    "isolated_frame": "Isolated frame",
    "sparse_frames": "Sparse frames",
    "short_sequence": "Short sequence",
    "full_relevant": "Full relevant",
    "full_video": "Full video",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_div(numerator, denominator):
    return numerator / denominator if denominator else None


def fmt(value, digits=3):
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def get_model_name(data):
    return data.get(
        "model_display_name",
        data.get("model", "Unknown model")
    )


def validate_identity(files):
    video_ids = {
        data.get("video_id")
        for data in files
        if data.get("video_id") is not None
    }

    if len(video_ids) != 1:
        raise ValueError(
            f"Input files do not all describe the same video: {video_ids}"
        )

    return next(iter(video_ids))


def summarize_experiment_a(data):
    """
    Prefer an existing summary when present, but compute missing values
    from query-level metrics. This supports both current A result variants.
    """
    queries = data.get("queries", [])
    existing = data.get("summary", {})

    metric_rows = [
        q.get("metrics", {})
        for q in queries
        if q.get("metrics") is not None
    ]

    def metric_mean(name):
        values = [
            row[name]
            for row in metric_rows
            if row.get(name) is not None
        ]
        return mean(values) if values else None

    total_queries = len(queries)

    event_level_misses = existing.get(
        "event_level_misses",
        sum(
            1
            for q in queries
            if q.get("metrics", {}).get("event_level_miss") is True
        )
    )

    validation_successes = existing.get(
        "validation_successes",
        sum(
            1
            for q in queries
            if q.get("validation_success") is True
        )
    )

    return {
        "model": data.get("model"),
        "model_display_name": get_model_name(data),
        "total_queries": total_queries,
        "mean_temporal_precision": existing.get(
            "mean_temporal_precision",
            metric_mean("temporal_precision")
        ),
        "mean_temporal_recall": existing.get(
            "mean_temporal_recall",
            metric_mean("temporal_recall")
        ),
        "mean_temporal_iou": existing.get(
            "mean_temporal_iou",
            metric_mean("temporal_iou")
        ),
        "mean_relevant_segment_recall": existing.get(
            "mean_relevant_segment_recall",
            metric_mean("relevant_segment_recall")
        ),
        "mean_percentage_video_retained": existing.get(
            "mean_percentage_video_retained",
            metric_mean("percentage_video_retained")
        ),
        "event_level_misses": event_level_misses,
        "event_level_miss_rate": safe_div(
            event_level_misses,
            total_queries
        ),
        "validation_successes": validation_successes,
        "valid_response_rate": safe_div(
            validation_successes,
            total_queries
        ),
    }

def find_b_summary(data):
    """
    Extract the scored Experiment B summary.
    """

    summary = data.get("summary")

    if not isinstance(summary, dict):
        raise ValueError(
            f"{get_model_name(data)} Experiment B file "
            "has no summary object."
        )

    gt = (
        summary.get("ground_truth_evidence")
        or summary.get("b_gt")
        or summary.get("B-GT")
    )

    ba = (
        summary.get("model_selected_evidence")
        or summary.get("b_a")
        or summary.get("B-A")
    )

    if not isinstance(gt, dict) or not isinstance(ba, dict):
        raise ValueError(
            "Could not locate B-GT/B-A summaries for "
            f"{get_model_name(data)}."
        )

    suff = (
        summary.get("a_to_b_sufficiency")
        or summary.get("a->b_sufficiency")
        or {}
    )

    return {
        "model": data.get("model"),
        "model_display_name": get_model_name(data),
        "ground_truth_evidence": gt,
        "model_selected_evidence": ba,
        "a_to_b_sufficiency": suff,
    }
    
    

def summarize_experiment_c(data):
    summaries = data.get("condition_summaries")
    if not isinstance(summaries, dict):
        raise ValueError(
            f"{get_model_name(data)} Experiment C file has no "
            "condition_summaries object."
        )

    return {
        "model": data.get("model"),
        "model_display_name": get_model_name(data),
        "condition_summaries": summaries,
        "minimum_threshold_condition": data.get(
            "minimum_threshold_condition"
        ),
        "consistency": data.get("consistency"),
        "acceptable_accuracy_threshold": (
            data.get("configuration", {})
            .get("acceptable_accuracy_threshold")
        ),
    }


def pick(d, *names):
    for name in names:
        if name in d:
            return d[name]
    return None


def b_metric(summary, condition, *names):
    block = summary[condition]
    return pick(block, *names)


def sufficiency_value(summary):
    value = summary.get("a_to_b_sufficiency")

    if isinstance(value, (int, float)):
        return value

    if not isinstance(value, dict):
        return None

    return pick(
        value,
        "rate",
        "accuracy",
        "sufficiency",
        "value"
    )


def print_two_model_table(title, rows, left_name, right_name):
    print()
    print(title)
    print("-" * 78)
    print(
        f"{'Metric':<38}"
        f"{left_name:>19}"
        f"{right_name:>19}"
    )
    print("-" * 78)

    for label, left, right in rows:
        print(
            f"{label:<38}"
            f"{fmt(left):>19}"
            f"{fmt(right):>19}"
        )


def build_combined(
    a_reason2,
    a_cosmos3,
    b_reason2,
    b_cosmos3,
    c_reason2,
    c_cosmos3,
):
    video_id = validate_identity([
        a_reason2,
        a_cosmos3,
        b_reason2,
        b_cosmos3,
        c_reason2,
        c_cosmos3,
    ])

    a_r = summarize_experiment_a(a_reason2)
    a_c = summarize_experiment_a(a_cosmos3)

    b_r = find_b_summary(b_reason2)
    b_c = find_b_summary(b_cosmos3)

    c_r = summarize_experiment_c(c_reason2)
    c_c = summarize_experiment_c(c_cosmos3)

    return {
        "video_id": video_id,
        "models": {
            a_r["model"]: a_r["model_display_name"],
            a_c["model"]: a_c["model_display_name"],
        },
        "experiment_a": {
            a_r["model"]: a_r,
            a_c["model"]: a_c,
        },
        "experiment_b": {
            b_r["model"]: b_r,
            b_c["model"]: b_c,
        },
        "experiment_c": {
            c_r["model"]: c_r,
            c_c["model"]: c_c,
        },
    }


def print_report(combined):
    a = combined["experiment_a"]
    b = combined["experiment_b"]
    c = combined["experiment_c"]

    # Keep the command-line order stable for the current two models.
    reason2_key = next(
        key for key in a
        if "reason2" in key.lower()
    )
    cosmos3_key = next(
        key for key in a
        if key != reason2_key
    )

    reason2_name = a[reason2_key]["model_display_name"]
    cosmos3_name = a[cosmos3_key]["model_display_name"]

    print("=" * 78)
    print("PRELIMINARY LAS-VICA EVALUATION")
    print(f"Video: {combined['video_id']}")
    print("=" * 78)

    a_rows = [
        (
            "Temporal precision",
            a[reason2_key]["mean_temporal_precision"],
            a[cosmos3_key]["mean_temporal_precision"],
        ),
        (
            "Temporal recall",
            a[reason2_key]["mean_temporal_recall"],
            a[cosmos3_key]["mean_temporal_recall"],
        ),
        (
            "Temporal IoU",
            a[reason2_key]["mean_temporal_iou"],
            a[cosmos3_key]["mean_temporal_iou"],
        ),
        (
            "Relevant-segment recall",
            a[reason2_key]["mean_relevant_segment_recall"],
            a[cosmos3_key]["mean_relevant_segment_recall"],
        ),
        (
            "Video retained (%)",
            a[reason2_key]["mean_percentage_video_retained"],
            a[cosmos3_key]["mean_percentage_video_retained"],
        ),
        (
            "Event-level miss rate",
            a[reason2_key]["event_level_miss_rate"],
            a[cosmos3_key]["event_level_miss_rate"],
        ),
        (
            "Valid response rate",
            a[reason2_key]["valid_response_rate"],
            a[cosmos3_key]["valid_response_rate"],
        ),
    ]

    print_two_model_table(
        "EXPERIMENT A — Evidence Selection",
        a_rows,
        reason2_name,
        cosmos3_name,
    )

    b_rows = [
        (
            "B-GT answer accuracy",
            b_metric(
                b[reason2_key],
                "ground_truth_evidence",
                "answer_accuracy"
            ),
            b_metric(
                b[cosmos3_key],
                "ground_truth_evidence",
                "answer_accuracy"
            ),
        ),
        (
            "B-A answer accuracy",
            b_metric(
                b[reason2_key],
                "model_selected_evidence",
                "answer_accuracy"
            ),
            b_metric(
                b[cosmos3_key],
                "model_selected_evidence",
                "answer_accuracy"
            ),
        ),
        (
            "B-A evidence availability",
            b_metric(
                b[reason2_key],
                "model_selected_evidence",
                "evidence_availability_rate"
            ),
            b_metric(
                b[cosmos3_key],
                "model_selected_evidence",
                "evidence_availability_rate"
            ),
        ),
        (
            "B-GT required-claim recall",
            b_metric(
                b[reason2_key],
                "ground_truth_evidence",
                "mean_required_claim_recall",
                "required_claim_recall"
            ),
            b_metric(
                b[cosmos3_key],
                "ground_truth_evidence",
                "mean_required_claim_recall",
                "required_claim_recall"
            ),
        ),
        (
            "B-A required-claim recall",
            b_metric(
                b[reason2_key],
                "model_selected_evidence",
                "mean_required_claim_recall",
                "required_claim_recall", 
            ),
            b_metric(
                b[cosmos3_key],
                "model_selected_evidence",
                "mean_required_claim_recall",
                "required_claim_recall"
            ),
        ),
        (
            "B-GT temporal accuracy",
            b_metric(
                b[reason2_key],
                "ground_truth_evidence",
                "mean_temporal_relation_accuracy",
                "temporal_relation_accuracy"
            ),
            b_metric(
                b[cosmos3_key],
                "ground_truth_evidence",
                "mean_temporal_relation_accuracy",
                "temporal_relation_accuracy"
            ),
        ),
        (
            "B-A temporal accuracy",
            b_metric(
                b[reason2_key],
                "model_selected_evidence",
                "mean_temporal_relation_accuracy",
                "temporal_relation_accuracy"
            ),
            b_metric(
                b[cosmos3_key],
                "model_selected_evidence",
                "mean_temporal_relation_accuracy",
                "temporal_relation_accuracy"
            ),
        ),
        (
            "A->B sufficiency",
            sufficiency_value(b[reason2_key]),
            sufficiency_value(b[cosmos3_key]),
        ),
    ]

    print_two_model_table(
        "EXPERIMENT B — Evidence-Conditioned Reasoning",
        b_rows,
        reason2_name,
        cosmos3_name,
    )

    for metric_key, title in [
        ("answer_accuracy", "EXPERIMENT C — Answer Accuracy"),
        (
            "temporal_order_accuracy",
            "EXPERIMENT C — Temporal-Order Accuracy"
        ),
        (
            "event_attribution_accuracy",
            "EXPERIMENT C — Event-Attribution Accuracy"
        ),
    ]:
        rows = []

        for condition in CONDITION_ORDER:
            r_block = c[reason2_key]["condition_summaries"].get(
                condition, {}
            )
            c_block = c[cosmos3_key]["condition_summaries"].get(
                condition, {}
            )

            rows.append((
                CONDITION_LABELS[condition],
                r_block.get(metric_key),
                c_block.get(metric_key),
            ))

        print_two_model_table(
            title,
            rows,
            reason2_name,
            cosmos3_name,
        )

    print()
    print("EXPERIMENT C — Evidence Threshold")
    print("-" * 78)

    for key in [reason2_key, cosmos3_key]:
        model = c[key]
        threshold = model.get("acceptable_accuracy_threshold")
        minimum = model.get("minimum_threshold_condition")

        if minimum:
            condition = minimum.get("condition")
            accuracy = minimum.get("answer_accuracy")
            result = (
                f"{CONDITION_LABELS.get(condition, condition)} "
                f"(accuracy={fmt(accuracy)})"
            )
        else:
            result = "Not reached"

        print(
            f"{model['model_display_name']:<25}"
            f"threshold={fmt(threshold):<8}"
            f"{result}"
        )

    print()
    print(
        "Note: Experiment C frame-based and continuous-video evidence "
        "budgets are reported separately in the source scoring files; "
        "they are not treated as a single duration scale."
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Combine scored LAS-VICA Experiments A, B, and C "
            "for Cosmos-Reason2 and Cosmos3."
        )
    )

    parser.add_argument("--reason2-a", required=True)
    parser.add_argument("--cosmos3-a", required=True)
    parser.add_argument("--reason2-b", required=True)
    parser.add_argument("--cosmos3-b", required=True)
    parser.add_argument("--reason2-c", required=True)
    parser.add_argument("--cosmos3-c", required=True)

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional output JSON path. Default: "
            "results/combined/<video_id>_combined_results.json"
        ),
    )

    args = parser.parse_args()

    inputs = {
        "a_reason2": load_json(args.reason2_a),
        "a_cosmos3": load_json(args.cosmos3_a),
        "b_reason2": load_json(args.reason2_b),
        "b_cosmos3": load_json(args.cosmos3_b),
        "c_reason2": load_json(args.reason2_c),
        "c_cosmos3": load_json(args.cosmos3_c),
    }

    combined = build_combined(**inputs)
    print_report(combined)

    output_path = args.output

    if output_path is None:
        output_path = os.path.join(
            "results",
            "combined",
            f"{combined['video_id']}_combined_results.json",
        )

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    print()
    print(f"Saved combined JSON to: {output_path}")


if __name__ == "__main__":
    main()
