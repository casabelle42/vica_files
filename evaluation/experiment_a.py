#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime


PROJECT_ROOT = "/home/las_edge_account/LAS-VICA"

DEFAULT_PROMPT = os.path.join(
    PROJECT_ROOT,
    "prompts",
    "experiment_a.txt"
)

DEFAULT_RESULTS_DIR = os.path.join(
    PROJECT_ROOT,
    "results",
    "experiment_a"
)


# ----------------------------------------------------------------------
# Model configurations
# ----------------------------------------------------------------------

MODEL_CONFIGS = {
    "cosmos3": {
        "display_name": "Cosmos3 Edge",
        "container": "cosmos3-local",
        "script": "/workspace/models/cosmos3-edge/cosmos3_infer.py",
        "response_start": "=== Cosmos3 Edge Response ===",
        "response_end": "=== End Response ===",
    },
    "cosmos_reason2": {
        "display_name": "Cosmos-Reason2",
        "container": "cosmos-reason2",
        "script": "/workspace/models/cosmos-reason2/cosmos-reason2_infer.py",
        "response_start": "=== Cosmos-Reason2 Response ===",
        "response_end": "=== End Response ===",
    },
}


# ----------------------------------------------------------------------
# File loading
# ----------------------------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

def resolve_video_path(annotation_path, annotation):
    """
    Expected dataset structure:

        videos/counterfactual_vids/
            annotations/
                IMG_2460.json
            data/
                IMG_2460.MOV

    The annotations and data directories are siblings.
    """

    annotation_dir = os.path.dirname(
        os.path.abspath(annotation_path)
    )

    dataset_root = os.path.dirname(
        annotation_dir
    )

    data_dir = os.path.join(
        dataset_root,
        "data"
    )

    video_path = os.path.normpath(
        os.path.join(
            data_dir,
            annotation["video_file"]
        )
    )

    if not os.path.exists(video_path):
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    return video_path


def host_to_container_path(host_path):
    """
    Convert a path under PROJECT_ROOT to its equivalent
    /workspace path inside the Docker container.
    """

    host_path = os.path.abspath(host_path)
    project_root = os.path.abspath(PROJECT_ROOT)

    relative = os.path.relpath(
        host_path,
        project_root
    )

    if relative.startswith(".."):
        raise RuntimeError(
            f"Path is outside PROJECT_ROOT: {host_path}"
        )

    return os.path.join(
        "/workspace",
        relative
    )


# ----------------------------------------------------------------------
# Experiment A prompt
# ----------------------------------------------------------------------

def build_experiment_a_prompt(
    frozen_instructions,
    analyst_query
):
    return (
        frozen_instructions.rstrip()
        + "\n\nAnalyst query:\n"
        + analyst_query.strip()
    )


# ----------------------------------------------------------------------
# Docker model execution
# ----------------------------------------------------------------------

def run_model(
    model_name,
    video_path,
    question,
    sample_fps
):
    if model_name not in MODEL_CONFIGS:
        raise ValueError(
            f"Unknown model: {model_name}"
        )

    config = MODEL_CONFIGS[model_name]

    container_video_path = host_to_container_path(
        video_path
    )

    command = [
        "docker",
        "run",
        "--rm",

        "--runtime",
        "nvidia",

        "--ipc=host",

        "--ulimit",
        "memlock=-1",

        "--ulimit",
        "stack=67108864",

        "-v",
        f"{PROJECT_ROOT}:/workspace",

        "--entrypoint",
        "python3",

        config["container"],

        config["script"],

        "--video-path",
        container_video_path,

        "--sample-fps",
        str(sample_fps),

        "--question",
        question,
    ]

    print(
        f"Running {config['display_name']} "
        f"at {sample_fps} FPS..."
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    return {
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ----------------------------------------------------------------------
# Extract model response
# ----------------------------------------------------------------------

def extract_model_response(stdout, model_name):
    """
    Extract the model response using the output markers
    configured for the selected model.
    """

    config = MODEL_CONFIGS[model_name]

    start_marker = re.escape(
        config["response_start"]
    )

    end_marker = re.escape(
        config["response_end"]
    )

    pattern = re.compile(
        start_marker
        + r"\s*(.*?)\s*"
        + end_marker,
        re.DOTALL
    )

    match = pattern.search(stdout)

    if match:
        return match.group(1).strip()

    return stdout.strip()


# ----------------------------------------------------------------------
# Parse Experiment A JSON
# ----------------------------------------------------------------------

def strip_markdown_json_fence(text):
    """
    Remove a Markdown JSON fence if the model returned:

        ```json
        {...}
        ```

    or:

        ```
        {...}
        ```
    """

    text = text.strip()

    match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return text


def extract_json_object(text):
    """
    Extract the first valid JSON object from a model response.

    This allows a model to emit reasoning or other text before or
    after its structured Experiment A response while preserving the
    complete raw response separately for auditing.
    """

    if not text:
        return None

    text = text.strip()

    # First try the complete response.
    try:
        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    # Otherwise search for the first valid JSON object.
    decoder = json.JSONDecoder()

    for index, char in enumerate(text):

        if char != "{":
            continue

        try:
            data, _ = decoder.raw_decode(
                text[index:]
            )

            if isinstance(data, dict):
                return data

        except json.JSONDecodeError:
            continue

    return None

def validation_failure(
    data,
    message,
    status="invalid_format"
):
    """
    Convenience function for constructing validation results.
    """

    return {
        "parse_success": True,
        "validation_success": False,
        "validation_error": message,
        "response_status": status,
        "parsed": data,
    }


def parse_experiment_a_response(response_text):
    """
    Parse and validate an Experiment A response.

    Important distinction:

    parse_success:
        Was valid JSON returned?

    validation_success:
        Does that JSON satisfy the Experiment A response contract?

    response_status:
        valid
        invalid_format
        inconsistent_evidence
    """
    
    cleaned = strip_markdown_json_fence(
        response_text
    )
    
    data = extract_json_object(
        cleaned
    )
    
    if data is None:
        return {
            "parse_success": False,
            "validation_success": False,
            "validation_error": (
                "No valid JSON object found in model response"
            ),
            "response_status": "invalid_format",
            "parsed": None,
        }

    if not isinstance(data, dict):
        return validation_failure(
            data,
            "Top-level response is not an object"
        )

    sufficient = data.get(
        "sufficient_evidence_identified"
    )

    if not isinstance(sufficient, bool):
        return validation_failure(
            data,
            (
                "sufficient_evidence_identified "
                "must be boolean"
            )
        )

    evidence = data.get("evidence")

    if not isinstance(evidence, list):
        return validation_failure(
            data,
            "evidence must be a list"
        )

    # --------------------------------------------------------------
    # Logical consistency checks
    # --------------------------------------------------------------

    if sufficient and len(evidence) == 0:
        return validation_failure(
            data,
            (
                "sufficient_evidence_identified is true "
                "but evidence is empty"
            ),
            status="inconsistent_evidence"
        )

    if not sufficient and len(evidence) > 0:
        return validation_failure(
            data,
            (
                "sufficient_evidence_identified is false "
                "but evidence intervals were provided"
            ),
            status="inconsistent_evidence"
        )

    # --------------------------------------------------------------
    # Validate individual intervals
    # --------------------------------------------------------------

    for i, interval in enumerate(evidence):

        if not isinstance(interval, dict):
            return validation_failure(
                data,
                f"Evidence item {i} is not an object"
            )

        start = interval.get("start")
        end = interval.get("end")

        if not isinstance(
            start,
            (int, float)
        ):
            return validation_failure(
                data,
                f"Evidence item {i} has invalid start"
            )

        if not isinstance(
            end,
            (int, float)
        ):
            return validation_failure(
                data,
                f"Evidence item {i} has invalid end"
            )

        if start < 0:
            return validation_failure(
                data,
                f"Evidence item {i} has negative start"
            )

        if end < start:
            return validation_failure(
                data,
                f"Evidence item {i}: end < start"
            )

    return {
        "parse_success": True,
        "validation_success": True,
        "validation_error": None,
        "response_status": "valid",
        "parsed": data,
    }


# ----------------------------------------------------------------------
# Interval utilities
# ----------------------------------------------------------------------

def merge_intervals(intervals):
    """
    Merge overlapping or adjacent intervals.

    Example:

        [[9, 14], [14, 24]]

    becomes:

        [[9, 24]]
    """

    if not intervals:
        return []

    intervals = sorted(
        [
            [float(start), float(end)]
            for start, end in intervals
        ],
        key=lambda x: x[0]
    )

    merged = [intervals[0]]

    for start, end in intervals[1:]:

        last = merged[-1]

        if start <= last[1]:
            last[1] = max(
                last[1],
                end
            )

        else:
            merged.append(
                [start, end]
            )

    return merged


def interval_duration(intervals):
    return sum(
        end - start
        for start, end in merge_intervals(intervals)
    )


def intersection_duration(a, b):
    """
    Calculate total temporal intersection between
    two sets of intervals.
    """

    a = merge_intervals(a)
    b = merge_intervals(b)

    total = 0.0

    i = 0
    j = 0

    while i < len(a) and j < len(b):

        start = max(
            a[i][0],
            b[j][0]
        )

        end = min(
            a[i][1],
            b[j][1]
        )

        if end > start:
            total += end - start

        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1

    return total


def intervals_overlap(a, b):
    """
    Return True when two intervals have
    positive-duration overlap.
    """

    return (
        min(a[1], b[1])
        >
        max(a[0], b[0])
    )


# ----------------------------------------------------------------------
# Finalized annotation access
# ----------------------------------------------------------------------

def get_evidence_ground_truth(query):
    """
    Return the finalized Experiment A evidence annotations.

    relevant_intervals:
        All temporal evidence relevant to the query.

    minimal_sufficient_intervals:
        The smallest annotated evidence set sufficient to answer.

    hard_negative_intervals:
        Plausible but misleading evidence for the query.

    excluded_intervals:
        Explicitly non-relevant evidence.

    relevant_segments:
        Semantic segments relevant to the query. These remain useful
        for segment/event coverage but are no longer used as the
        primary temporal ground truth.
    """

    evidence = (
        query["ground_truth"]
        ["evidence"]
    )

    return {
        "relevant_intervals":
            evidence.get(
                "relevant_intervals",
                []
            ),

        "minimal_sufficient_intervals":
            evidence.get(
                "minimal_sufficient_intervals",
                []
            ),

        "hard_negative_intervals":
            evidence.get(
                "hard_negative_intervals",
                []
            ),

        "excluded_intervals":
            evidence.get(
                "excluded_intervals",
                []
            ),

        "relevant_segments":
            evidence.get(
                "relevant_segments",
                []
            ),
    }


def get_relevant_segment_intervals(
    annotation,
    relevant_segments
):
    """
    Convert relevant semantic segment IDs into intervals.

    These intervals are used only for relevant-segment coverage,
    not for primary temporal precision/recall/IoU.

    Segment intervals are read from the finalized annotation's
    top-level "segments" array.
    """

    intervals = []

    segments = annotation.get(
        "segments",
        []
    )

    # Build a lookup by explicit segment_id rather than assuming
    # segment IDs always equal list positions.
    segment_lookup = {
        segment["segment_id"]: segment
        for segment in segments
        if isinstance(segment, dict)
        and "segment_id" in segment
    }

    for segment_id in relevant_segments:

        if segment_id not in segment_lookup:
            raise KeyError(
                f"Relevant segment ID {segment_id} "
                f"not found in annotation segments"
            )

        segment = segment_lookup[
            segment_id
        ]

        start = segment.get("start")
        end = segment.get("end")

        if not isinstance(
            start,
            (int, float)
        ):
            raise ValueError(
                f"Segment {segment_id} has "
                f"invalid start: {start}"
            )

        if not isinstance(
            end,
            (int, float)
        ):
            raise ValueError(
                f"Segment {segment_id} has "
                f"invalid end: {end}"
            )

        if end < start:
            raise ValueError(
                f"Segment {segment_id} has "
                f"end < start"
            )

        intervals.append(
            [
                float(start),
                float(end)
            ]
        )

    return intervals

# ----------------------------------------------------------------------
# Prediction validation
# ----------------------------------------------------------------------

def selected_intervals_within_video(
    selected_intervals,
    video_duration
):
    """
    Ensure all predicted evidence intervals fall within
    the annotated video duration.
    """

    for start, end in selected_intervals:

        if start < 0:
            return False

        if end < start:
            return False

        if end > video_duration:
            return False

    return True


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

def make_zero_metrics(
    evidence_gt,
    annotation
):
    """
    Return zero-valued task metrics for an executed query that
    failed to produce usable evidence.

    Metrics that are not applicable to the query remain None.
    """

    relevant_intervals = (
        evidence_gt["relevant_intervals"]
    )

    minimal_intervals = (
        evidence_gt[
            "minimal_sufficient_intervals"
        ]
    )

    hard_negative_intervals = (
        evidence_gt[
            "hard_negative_intervals"
        ]
    )

    excluded_intervals = (
        evidence_gt[
            "excluded_intervals"
        ]
    )

    relevant_segments = (
        evidence_gt["relevant_segments"]
    )

    relevant_duration = interval_duration(
        relevant_intervals
    )

    minimal_duration = interval_duration(
        minimal_intervals
    )

    hard_negative_duration = interval_duration(
        hard_negative_intervals
    )

    excluded_duration = interval_duration(
        excluded_intervals
    )

    return {
        "selected_duration_seconds":
            0.0,

        "relevant_duration_seconds":
            relevant_duration,

        "intersection_seconds":
            0.0,

        "temporal_precision":
            0.0,

        "temporal_recall":
            0.0,

        "temporal_iou":
            0.0,

        "percentage_video_retained":
            0.0,

        "minimal_sufficient_duration_seconds":
            minimal_duration,

        "minimal_sufficient_intersection_seconds":
            0.0,

        "minimal_sufficient_coverage":
            (
                0.0
                if minimal_duration > 0
                else None
            ),

        "minimal_sufficient_fully_covered":
            (
                False
                if minimal_duration > 0
                else None
            ),

        "hard_negative_duration_seconds":
            hard_negative_duration,

        "hard_negative_selected_seconds":
            0.0,

        "hard_negative_fp_rate":
            (
                0.0
                if hard_negative_duration > 0
                else None
            ),

        "excluded_duration_seconds":
            excluded_duration,

        "excluded_selected_seconds":
            0.0,

        "relevant_segments_found":
            0,

        "relevant_segments_total":
            len(relevant_segments),

        "relevant_segment_recall":
            (
                0.0
                if relevant_segments
                else None
            ),

        "event_level_miss":
            (
                True
                if relevant_segments
                else None
            ),
    }


def calculate_metrics(
    evidence_gt,
    selected_intervals,
    annotation
):
    """
    Calculate finalized Experiment A metrics.

    Primary temporal metrics use relevant_intervals.

    relevant_segments are evaluated separately to preserve
    semantic/event coverage information.

    hard_negative_intervals and excluded_intervals are also
    evaluated separately because they have different meanings.
    """

    video_duration = float(
        annotation["duration"]
    )

    # --------------------------------------------------------------
    # Ground-truth evidence
    # --------------------------------------------------------------

    relevant_intervals = merge_intervals(
        evidence_gt["relevant_intervals"]
    )

    minimal_intervals = merge_intervals(
        evidence_gt[
            "minimal_sufficient_intervals"
        ]
    )

    hard_negative_intervals = merge_intervals(
        evidence_gt[
            "hard_negative_intervals"
        ]
    )

    excluded_intervals = merge_intervals(
        evidence_gt[
            "excluded_intervals"
        ]
    )

    relevant_segments = (
        evidence_gt["relevant_segments"]
    )

    relevant_segment_intervals = (
        get_relevant_segment_intervals(
            annotation,
            relevant_segments
        )
    )

    selected_merged = merge_intervals(
        selected_intervals
    )

    # --------------------------------------------------------------
    # Primary temporal metrics
    # --------------------------------------------------------------

    relevant_duration = interval_duration(
        relevant_intervals
    )

    selected_duration = interval_duration(
        selected_merged
    )

    intersection = intersection_duration(
        relevant_intervals,
        selected_merged
    )

    union = (
        relevant_duration
        + selected_duration
        - intersection
    )

    temporal_precision = (
        intersection / selected_duration
        if selected_duration > 0
        else 0.0
    )

    temporal_recall = (
        intersection / relevant_duration
        if relevant_duration > 0
        else 0.0
    )

    temporal_iou = (
        intersection / union
        if union > 0
        else 0.0
    )

    percentage_video_retained = (
        100.0
        * selected_duration
        / video_duration
        if video_duration > 0
        else 0.0
    )

    # --------------------------------------------------------------
    # Minimal-sufficient evidence coverage
    # --------------------------------------------------------------

    minimal_duration = interval_duration(
        minimal_intervals
    )

    minimal_intersection = intersection_duration(
        minimal_intervals,
        selected_merged
    )

    if minimal_duration > 0:

        minimal_coverage = (
            minimal_intersection
            / minimal_duration
        )

        minimal_fully_covered = (
            minimal_coverage >= 0.999
        )

    else:

        minimal_coverage = None
        minimal_fully_covered = None

    # --------------------------------------------------------------
    # Hard-negative false-positive behavior
    # --------------------------------------------------------------

    hard_negative_duration = interval_duration(
        hard_negative_intervals
    )

    hard_negative_selected = intersection_duration(
        hard_negative_intervals,
        selected_merged
    )

    hard_negative_fp_rate = (
        hard_negative_selected
        / hard_negative_duration
        if hard_negative_duration > 0
        else None
    )

    # --------------------------------------------------------------
    # Excluded evidence
    # --------------------------------------------------------------

    excluded_duration = interval_duration(
        excluded_intervals
    )

    excluded_selected = intersection_duration(
        excluded_intervals,
        selected_merged
    )

    # --------------------------------------------------------------
    # Relevant semantic-segment recall
    #
    # Keep semantic segments separate even when temporally adjacent.
    # A model may achieve high temporal recall while still missing
    # a short but semantically important event.
    # --------------------------------------------------------------

    segments_found = 0

    for gt_segment in relevant_segment_intervals:

        found = any(
            intervals_overlap(
                gt_segment,
                selected
            )
            for selected in selected_merged
        )

        if found:
            segments_found += 1

    segment_total = len(
        relevant_segment_intervals
    )

    if segment_total > 0:

        segment_recall = (
            segments_found
            / segment_total
        )

        event_level_miss = (
            segments_found
            < segment_total
        )

    else:

        segment_recall = None
        event_level_miss = None

    return {
        "selected_duration_seconds":
            selected_duration,

        "relevant_duration_seconds":
            relevant_duration,

        "intersection_seconds":
            intersection,

        "temporal_precision":
            temporal_precision,

        "temporal_recall":
            temporal_recall,

        "temporal_iou":
            temporal_iou,

        "percentage_video_retained":
            percentage_video_retained,

        "minimal_sufficient_duration_seconds":
            minimal_duration,

        "minimal_sufficient_intersection_seconds":
            minimal_intersection,

        "minimal_sufficient_coverage":
            minimal_coverage,

        "minimal_sufficient_fully_covered":
            minimal_fully_covered,

        "hard_negative_duration_seconds":
            hard_negative_duration,

        "hard_negative_selected_seconds":
            hard_negative_selected,

        "hard_negative_fp_rate":
            hard_negative_fp_rate,

        "excluded_duration_seconds":
            excluded_duration,

        "excluded_selected_seconds":
            excluded_selected,

        "relevant_segments_found":
            segments_found,

        "relevant_segments_total":
            segment_total,

        "relevant_segment_recall":
            segment_recall,

        "event_level_miss":
            event_level_miss,
    }


# ----------------------------------------------------------------------
# Query-level output
# ----------------------------------------------------------------------

def print_query_metrics(
    query_id,
    metrics
):
    print(f"\n{query_id}")

    print(
        f"  Precision:               "
        f"{metrics['temporal_precision']:.3f}"
    )

    print(
        f"  Recall:                  "
        f"{metrics['temporal_recall']:.3f}"
    )

    print(
        f"  IoU:                     "
        f"{metrics['temporal_iou']:.3f}"
    )

    print(
        f"  Video retained:          "
        f"{metrics['percentage_video_retained']:.1f}%"
    )

    segment_recall = (
        metrics["relevant_segment_recall"]
    )

    if segment_recall is not None:

        print(
            f"  Segment recall:          "
            f"{segment_recall:.3f} "
            f"("
            f"{metrics['relevant_segments_found']}/"
            f"{metrics['relevant_segments_total']}"
            f")"
        )

    else:

        print(
            "  Segment recall:          N/A"
        )

    minimal_coverage = (
        metrics[
            "minimal_sufficient_coverage"
        ]
    )

    if minimal_coverage is not None:

        print(
            f"  Minimal coverage:        "
            f"{minimal_coverage:.3f}"
        )

        print(
            f"  Minimal fully covered:   "
            f"{metrics['minimal_sufficient_fully_covered']}"
        )

    else:

        print(
            "  Minimal coverage:        N/A"
        )

    hard_negative_fp = (
        metrics["hard_negative_fp_rate"]
    )

    if hard_negative_fp is not None:

        print(
            f"  Hard-negative FP rate:   "
            f"{hard_negative_fp:.3f}"
        )

        print(
            f"  Hard-negative selected:  "
            f"{metrics['hard_negative_selected_seconds']:.3f}s"
        )

    else:

        print(
            "  Hard-negative FP rate:   N/A"
        )

    print(
        f"  Excluded selected:       "
        f"{metrics['excluded_selected_seconds']:.3f}s"
    )


def mean(values):
    if not values:
        return None

    return sum(values) / len(values)


def non_none_metric_values(
    scored,
    metric_name
):
    return [
        q["metrics"][metric_name]
        for q in scored
        if q["metrics"].get(metric_name)
        is not None
    ]


# ----------------------------------------------------------------------
# Experiment summary
# ----------------------------------------------------------------------

def print_final_summary(results):

    queries = results["queries"]
    total = len(queries)

    # --------------------------------------------------------------
    # Scoring policy
    #
    # Every successfully executed query contributes to task
    # performance. Invalid, malformed, or otherwise unusable model
    # responses receive zero-valued metrics.
    #
    # Infrastructure/model execution failures remain unscored and
    # therefore have metrics = None.
    # --------------------------------------------------------------

    scored = [
        q
        for q in queries
        if q.get("metrics") is not None
    ]

    execution_successes = sum(
        1
        for q in queries
        if q.get("execution_success")
    )

    parse_successes = sum(
        1
        for q in queries
        if q.get("parse_success")
    )

    validation_successes = sum(
        1
        for q in queries
        if q.get("validation_success")
    )

    inconsistent_responses = sum(
        1
        for q in queries
        if q.get("response_status")
        == "inconsistent_evidence"
    )

    out_of_bounds_responses = sum(
        1
        for q in queries
        if q.get("response_status")
        == "out_of_bounds_evidence"
    )

    sufficient_claimed = sum(
        1
        for q in queries
        if (
            isinstance(
                q.get("parsed_response"),
                dict
            )
            and
            q["parsed_response"].get(
                "sufficient_evidence_identified"
            ) is True
        )
    )

    zero_evidence = sum(
        1
        for q in queries
        if (
            q.get("execution_success")
            and
            q.get("metrics") is not None
            and
            q["metrics"].get(
                "selected_duration_seconds"
            ) == 0.0
        )
    )

    # --------------------------------------------------------------
    # Event-level misses
    # --------------------------------------------------------------

    event_level_scored = [
        q
        for q in scored
        if q["metrics"].get(
            "event_level_miss"
        ) is not None
    ]

    event_level_misses = sum(
        1
        for q in event_level_scored
        if q["metrics"][
            "event_level_miss"
        ] is True
    )

    # --------------------------------------------------------------
    # Aggregate primary metrics
    # --------------------------------------------------------------

    mean_precision = mean(
        non_none_metric_values(
            scored,
            "temporal_precision"
        )
    )

    mean_recall = mean(
        non_none_metric_values(
            scored,
            "temporal_recall"
        )
    )

    mean_iou = mean(
        non_none_metric_values(
            scored,
            "temporal_iou"
        )
    )

    mean_segment_recall = mean(
        non_none_metric_values(
            scored,
            "relevant_segment_recall"
        )
    )

    mean_video_retained = mean(
        non_none_metric_values(
            scored,
            "percentage_video_retained"
        )
    )

    # --------------------------------------------------------------
    # Minimal-sufficient evidence summary
    # --------------------------------------------------------------

    minimal_queries = [
        q
        for q in scored
        if q["metrics"].get(
            "minimal_sufficient_coverage"
        ) is not None
    ]

    mean_minimal_coverage = mean(
        non_none_metric_values(
            scored,
            "minimal_sufficient_coverage"
        )
    )

    minimal_fully_covered_count = sum(
        1
        for q in minimal_queries
        if q["metrics"].get(
            "minimal_sufficient_fully_covered"
        ) is True
    )

    minimal_full_coverage_rate = (
        minimal_fully_covered_count
        / len(minimal_queries)
        if minimal_queries
        else None
    )

    # --------------------------------------------------------------
    # Hard-negative summary
    # --------------------------------------------------------------

    hard_negative_queries = [
        q
        for q in scored
        if q["metrics"].get(
            "hard_negative_fp_rate"
        ) is not None
    ]

    mean_hard_negative_fp_rate = mean(
        non_none_metric_values(
            scored,
            "hard_negative_fp_rate"
        )
    )

    mean_hard_negative_selected = mean(
        non_none_metric_values(
            hard_negative_queries,
            "hard_negative_selected_seconds"
        )
    )

    # --------------------------------------------------------------
    # Excluded evidence summary
    # --------------------------------------------------------------

    mean_excluded_selected = mean(
        non_none_metric_values(
            scored,
            "excluded_selected_seconds"
        )
    )

    # --------------------------------------------------------------
    # Store summary
    # --------------------------------------------------------------

    summary = {
        "total_queries":
            total,

        "execution_successes":
            execution_successes,

        "parse_successes":
            parse_successes,

        "validation_successes":
            validation_successes,

        "inconsistent_responses":
            inconsistent_responses,

        "out_of_bounds_responses":
            out_of_bounds_responses,

        "sufficient_claimed":
            sufficient_claimed,

        "zero_evidence_outputs":
            zero_evidence,

        "scored_runs":
            len(scored),

        "event_level_misses":
            event_level_misses,

        "event_level_scored_queries":
            len(event_level_scored),

        "mean_temporal_precision":
            mean_precision,

        "mean_temporal_recall":
            mean_recall,

        "mean_temporal_iou":
            mean_iou,

        "mean_relevant_segment_recall":
            mean_segment_recall,

        "mean_percentage_video_retained":
            mean_video_retained,

        "minimal_sufficient_queries":
            len(minimal_queries),

        "mean_minimal_sufficient_coverage":
            mean_minimal_coverage,

        "minimal_sufficient_fully_covered":
            minimal_fully_covered_count,

        "minimal_sufficient_full_coverage_rate":
            minimal_full_coverage_rate,

        "hard_negative_queries":
            len(hard_negative_queries),

        "mean_hard_negative_fp_rate":
            mean_hard_negative_fp_rate,

        "mean_hard_negative_selected_seconds":
            mean_hard_negative_selected,

        "mean_excluded_selected_seconds":
            mean_excluded_selected,
    }

    results["summary"] = summary

    # --------------------------------------------------------------
    # Console output
    # --------------------------------------------------------------

    print("\n")
    print("=" * 60)
    print("Experiment A Summary")
    print("=" * 60)

    print(
        f"Model:                         "
        f"{results['model_display_name']}"
    )

    print(
        f"Video:                         "
        f"{results['video_id']}"
    )

    print(
        f"Sample FPS:                    "
        f"{results['configuration']['sample_fps']}"
    )

    print()

    print(
        f"Execution success:             "
        f"{execution_successes}/{total}"
    )

    print(
        f"JSON parseable:                "
        f"{parse_successes}/{total}"
    )

    print(
        f"Semantically valid:            "
        f"{validation_successes}/{total}"
    )

    print(
        f"Inconsistent responses:        "
        f"{inconsistent_responses}/{total}"
    )

    print(
        f"Out-of-bounds responses:       "
        f"{out_of_bounds_responses}/{total}"
    )

    print(
        f"Sufficient claimed:            "
        f"{sufficient_claimed}/{total}"
    )

    print(
        f"Zero-evidence outputs:          "
        f"{zero_evidence}/{total}"
    )

    print(
        f"Scored runs:                   "
        f"{len(scored)}/{total}"
    )

    if event_level_scored:

        print(
            f"Event-level misses:             "
            f"{event_level_misses}/"
            f"{len(event_level_scored)}"
        )

    else:

        print(
            "Event-level misses:             N/A"
        )

    if not scored:
        print("\nNo scored query results.")
        return summary

    print()

    print(
        f"Mean precision:                 "
        f"{mean_precision:.3f}"
    )

    print(
        f"Mean recall:                    "
        f"{mean_recall:.3f}"
    )

    print(
        f"Mean IoU:                       "
        f"{mean_iou:.3f}"
    )

    if mean_segment_recall is not None:

        print(
            f"Mean segment recall:            "
            f"{mean_segment_recall:.3f}"
        )

    else:

        print(
            "Mean segment recall:            N/A"
        )

    print(
        f"Mean video retained:            "
        f"{mean_video_retained:.1f}%"
    )

    if mean_minimal_coverage is not None:

        print(
            f"Mean minimal coverage:          "
            f"{mean_minimal_coverage:.3f}"
        )

        print(
            f"Minimal fully covered:          "
            f"{minimal_fully_covered_count}/"
            f"{len(minimal_queries)}"
        )

        print(
            f"Minimal full coverage rate:     "
            f"{minimal_full_coverage_rate:.3f}"
        )

    else:

        print(
            "Mean minimal coverage:          N/A"
        )

    if mean_hard_negative_fp_rate is not None:

        print(
            f"Mean hard-negative FP rate:     "
            f"{mean_hard_negative_fp_rate:.3f}"
        )

        print(
            f"Hard-negative queries:          "
            f"{len(hard_negative_queries)}"
        )

    else:

        print(
            "Mean hard-negative FP rate:     N/A"
        )

    print(
        f"Mean excluded selected:         "
        f"{mean_excluded_selected:.3f}s"
    )

    return summary


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run and score Experiment A evidence triage."
        )
    )

    parser.add_argument(
        "--annotation",
        required=True,
        help="Path to annotation JSON."
    )

    parser.add_argument(
        "--model",
        choices=MODEL_CONFIGS.keys(),
        default="cosmos3",
        help="Model to evaluate."
    )

    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0,
        help="Video sampling FPS."
    )

    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Frozen Experiment A prompt file."
    )

    parser.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help="Directory for experiment results."
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load experiment inputs
    # ------------------------------------------------------------------

    annotation = load_json(
        args.annotation
    )

    frozen_prompt = load_text(
        args.prompt
    )

    video_path = resolve_video_path(
        args.annotation,
        annotation
    )

    model_config = MODEL_CONFIGS[
        args.model
    ]

    # ------------------------------------------------------------------
    # Experiment result record
    # ------------------------------------------------------------------

    results = {
        "experiment": "A",

        "model": args.model,

        "model_display_name":
            model_config["display_name"],

        "video_id":
            annotation["video_id"],

        "video_file":
            annotation["video_file"],

        "configuration": {
            "sample_fps":
                args.sample_fps,

            "prompt_file":
                os.path.relpath(
                    args.prompt,
                    PROJECT_ROOT
                ),

            "ground_truth_source":
                "finalized_evidence_annotations",
        },

        "queries": [],
    }

    total_queries = len(
        annotation["queries"]
    )

    # ------------------------------------------------------------------
    # Run every analyst query
    # ------------------------------------------------------------------

    for index, query in enumerate(
        annotation["queries"],
        start=1
    ):

        query_id = query["query_id"]

        print("\n")
        print("=" * 60)

        print(
            f"Query {index}/{total_queries}: "
            f"{query_id}"
        )

        print("=" * 60)

        print(
            query["query"]
        )

        # --------------------------------------------------------------
        # Load finalized evidence ground truth
        # --------------------------------------------------------------

        evidence_gt = (
            get_evidence_ground_truth(
                query
            )
        )

        # --------------------------------------------------------------
        # Build and run Experiment A prompt
        # --------------------------------------------------------------

        experiment_prompt = (
            build_experiment_a_prompt(
                frozen_prompt,
                query["query"]
            )
        )

        model_run = run_model(
            args.model,
            video_path,
            experiment_prompt,
            args.sample_fps
        )

        # --------------------------------------------------------------
        # Container/model execution failure
        # --------------------------------------------------------------

        if model_run["return_code"] != 0:

            print(
                "Model execution failed.",
                file=sys.stderr
            )

            print(
                model_run["stderr"],
                file=sys.stderr
            )

            results["queries"].append({
                "query_id":
                    query_id,

                "query":
                    query["query"],

                "ground_truth":
                    evidence_gt,

                "execution_success":
                    False,

                "return_code":
                    model_run["return_code"],

                "stdout":
                    model_run["stdout"],

                "stderr":
                    model_run["stderr"],

                "parse_success":
                    False,

                "validation_success":
                    False,

                "validation_error":
                    "Model execution failed",

                "response_status":
                    "execution_failure",

                "parsed_response":
                    None,

                "metrics":
                    None,
            })

            continue

        # --------------------------------------------------------------
        # Extract and parse response
        # --------------------------------------------------------------

        response_text = (
            extract_model_response(
                model_run["stdout"],
                args.model
            )
        )

        parsed = (
            parse_experiment_a_response(
                response_text
            )
        )

        query_result = {
            "query_id":
                query_id,

            "query":
                query["query"],

            "query_type":
                query.get("query_type"),

            "ground_truth": {
                "relevant_segments":
                    evidence_gt[
                        "relevant_segments"
                    ],

                "relevant_intervals":
                    evidence_gt[
                        "relevant_intervals"
                    ],

                "minimal_sufficient_intervals":
                    evidence_gt[
                        "minimal_sufficient_intervals"
                    ],

                "hard_negative_intervals":
                    evidence_gt[
                        "hard_negative_intervals"
                    ],

                "excluded_intervals":
                    evidence_gt[
                        "excluded_intervals"
                    ],
            },

            "execution_success":
                True,

            "return_code":
                model_run["return_code"],

            "raw_response":
                response_text,

            "parse_success":
                parsed["parse_success"],

            "validation_success":
                parsed["validation_success"],

            "validation_error":
                parsed["validation_error"],

            "response_status":
                parsed["response_status"],

            "parsed_response":
                parsed["parsed"],

            "metrics":
                None,
        }

        # --------------------------------------------------------------
        # Determine whether evidence is structurally usable
        # --------------------------------------------------------------

        can_score_evidence = (
            parsed["parse_success"]
            and isinstance(
                parsed["parsed"],
                dict
            )
            and isinstance(
                parsed["parsed"].get(
                    "evidence"
                ),
                list
            )
        )

        usable_evidence = False
        selected = []

        if can_score_evidence:

            evidence_items = (
                parsed["parsed"]["evidence"]
            )

            usable_evidence = all(
                isinstance(item, dict)
                and isinstance(
                    item.get("start"),
                    (int, float)
                )
                and isinstance(
                    item.get("end"),
                    (int, float)
                )
                and item["start"] >= 0
                and item["end"] >= item["start"]
                for item in evidence_items
            )

            if usable_evidence:

                selected = [
                    [
                        float(item["start"]),
                        float(item["end"])
                    ]
                    for item in evidence_items
                ]

                # ------------------------------------------------------
                # Prediction must also fall within the actual video.
                # ------------------------------------------------------

                if not selected_intervals_within_video(
                    selected,
                    annotation["duration"]
                ):

                    usable_evidence = False

                    query_result[
                        "validation_success"
                    ] = False

                    query_result[
                        "validation_error"
                    ] = (
                        "One or more evidence intervals "
                        "fall outside the video duration"
                    )

                    query_result[
                        "response_status"
                    ] = "out_of_bounds_evidence"

        # --------------------------------------------------------------
        # Score model response
        #
        # Every successfully executed query contributes to task
        # performance.
        #
        # Valid usable evidence:
        #     Score selected intervals normally.
        #
        # Parse/schema/semantic/out-of-bounds failure:
        #     Assign zero task-performance scores.
        #
        # Container/model execution failure:
        #     metrics = None.
        # --------------------------------------------------------------

        if usable_evidence:

            metrics = calculate_metrics(
                evidence_gt,
                selected,
                annotation
            )

        else:

            metrics = make_zero_metrics(
                evidence_gt,
                annotation
            )

        query_result["metrics"] = metrics

        # --------------------------------------------------------------
        # Display response
        # --------------------------------------------------------------

        print("\nModel response:")

        if (
            parsed["parse_success"]
            and isinstance(
                parsed["parsed"],
                dict
            )
        ):

            print(
                json.dumps(
                    parsed["parsed"],
                    indent=2
                )
            )

        else:

            print(response_text)

        # --------------------------------------------------------------
        # Report output-compliance problems separately from scoring
        # --------------------------------------------------------------

        if not parsed["parse_success"]:

            print(
                "\nWARNING: Response could not be "
                "parsed as Experiment A JSON."
            )

        elif (
            query_result["response_status"]
            == "out_of_bounds_evidence"
        ):

            print(
                "\nWARNING: Response contained "
                "evidence outside the video duration."
            )

        elif not parsed["validation_success"]:

            print(
                "\nWARNING: Response failed "
                "semantic/schema validation:"
            )

            print(
                f"  {parsed['validation_error']}"
            )

        elif not usable_evidence:

            print(
                "\nWARNING: Response contained "
                "malformed evidence intervals."
            )

        print_query_metrics(
            query_id,
            metrics
        )

        # --------------------------------------------------------------
        # Store completed query result
        # --------------------------------------------------------------

        results["queries"].append(
            query_result
        )

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------

    print_final_summary(
        results
    )

    # ------------------------------------------------------------------
    # Save complete experiment results
    # ------------------------------------------------------------------

    os.makedirs(
        args.results_dir,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_name = (
        f"{annotation['video_id']}_"
        f"{args.model}_"
        f"{timestamp}.json"
    )

    output_path = os.path.join(
        args.results_dir,
        output_name
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"\nResults saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()
