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

    try:
        data = json.loads(cleaned)

    except json.JSONDecodeError as exc:
        return {
            "parse_success": False,
            "validation_success": False,
            "validation_error": (
                f"Invalid JSON: {exc}"
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
# Ground truth
# ----------------------------------------------------------------------

def get_ground_truth_intervals(
    annotation,
    query
):
    """
    Convert relevant segment indices into temporal intervals.
    """

    segment_ids = (
        query["ground_truth"]
        ["evidence"]
        ["relevant_segments"]
    )

    intervals = []

    for segment_id in segment_ids:

        if (
            segment_id < 0
            or segment_id >= len(
                annotation["timestamps"]
            )
        ):
            raise IndexError(
                f"Invalid relevant segment "
                f"{segment_id}"
            )

        intervals.append(
            annotation["timestamps"][segment_id]
        )

    return intervals


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

def make_zero_metrics(
    gt_intervals,
    relevant_segments
):
    ground_truth_duration = sum(
        end - start
        for start, end in gt_intervals
    )

    return {
        "selected_duration_seconds": 0.0,
        "ground_truth_duration_seconds": ground_truth_duration,
        "intersection_seconds": 0.0,
        "temporal_precision": 0.0,
        "temporal_recall": 0.0,
        "temporal_iou": 0.0,
        "percentage_video_retained": 0.0,
        "relevant_segments_found": 0,
        "relevant_segments_total": len(relevant_segments),
        "relevant_segment_recall": 0.0,
        "event_level_miss": True,
    }
        
def calculate_metrics(
    ground_truth_intervals,
    selected_intervals,
    video_duration
):
    """
    Calculate provisional Experiment A metrics.

    These are segment-derived metrics until finer
    relevant_intervals/minimum_sufficient_intervals
    are available.
    """

    gt_merged = merge_intervals(
        ground_truth_intervals
    )

    selected_merged = merge_intervals(
        selected_intervals
    )

    gt_duration = interval_duration(
        gt_merged
    )

    selected_duration = interval_duration(
        selected_merged
    )

    intersection = intersection_duration(
        gt_merged,
        selected_merged
    )

    union = (
        gt_duration
        + selected_duration
        - intersection
    )

    temporal_precision = (
        intersection / selected_duration
        if selected_duration > 0
        else 0.0
    )

    temporal_recall = (
        intersection / gt_duration
        if gt_duration > 0
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
    # Relevant-segment recall
    #
    # Keep semantic segments separate even when they are temporally
    # adjacent. This lets us detect cases such as Q3 where the model
    # finds the exit event but misses the later return event.
    # --------------------------------------------------------------

    segments_found = 0

    for gt_segment in ground_truth_intervals:

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
        ground_truth_intervals
    )

    segment_recall = (
        segments_found / segment_total
        if segment_total > 0
        else 0.0
    )

    event_level_miss = (
        segments_found < segment_total
    )

    return {
        "selected_duration_seconds":
            selected_duration,

        "ground_truth_duration_seconds":
            gt_duration,

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
        f"  Precision:       "
        f"{metrics['temporal_precision']:.3f}"
    )

    print(
        f"  Recall:          "
        f"{metrics['temporal_recall']:.3f}"
    )

    print(
        f"  IoU:             "
        f"{metrics['temporal_iou']:.3f}"
    )

    print(
        f"  Video retained:  "
        f"{metrics['percentage_video_retained']:.1f}%"
    )

    print(
        f"  Segment recall:  "
        f"{metrics['relevant_segment_recall']:.3f} "
        f"("
        f"{metrics['relevant_segments_found']}/"
        f"{metrics['relevant_segments_total']}"
        f")"
    )


def mean(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


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

    # --------------------------------------------------------------
    # A zero-evidence output means the model produced no usable
    # evidence selection.
    #
    # This includes:
    #
    #   evidence = []
    #
    # as well as an executed response for which evidence was absent
    # or malformed and zero task metrics were therefore assigned.
    # --------------------------------------------------------------

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

    event_level_misses = sum(
        1
        for q in scored
        if q["metrics"].get(
            "event_level_miss"
        ) is True
    )

    # --------------------------------------------------------------
    # Aggregate task metrics
    # --------------------------------------------------------------

    if scored:

        mean_precision = mean([
            q["metrics"]["temporal_precision"]
            for q in scored
        ])

        mean_recall = mean([
            q["metrics"]["temporal_recall"]
            for q in scored
        ])

        mean_iou = mean([
            q["metrics"]["temporal_iou"]
            for q in scored
        ])

        mean_segment_recall = mean([
            q["metrics"][
                "relevant_segment_recall"
            ]
            for q in scored
        ])

        mean_video_retained = mean([
            q["metrics"][
                "percentage_video_retained"
            ]
            for q in scored
        ])

    else:

        mean_precision = None
        mean_recall = None
        mean_iou = None
        mean_segment_recall = None
        mean_video_retained = None

    # --------------------------------------------------------------
    # Store summary in results JSON
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

        "sufficient_claimed":
            sufficient_claimed,

        "zero_evidence_outputs":
            zero_evidence,

        "scored_runs":
            len(scored),

        "event_level_misses":
            event_level_misses,

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
        f"Model:                  "
        f"{results['model_display_name']}"
    )

    print(
        f"Video:                  "
        f"{results['video_id']}"
    )

    print(
        f"Sample FPS:             "
        f"{results['configuration']['sample_fps']}"
    )

    print()

    print(
        f"Execution success:      "
        f"{execution_successes}/{total}"
    )

    print(
        f"JSON parseable:         "
        f"{parse_successes}/{total}"
    )

    print(
        f"Semantically valid:     "
        f"{validation_successes}/{total}"
    )

    print(
        f"Inconsistent responses: "
        f"{inconsistent_responses}/{total}"
    )

    print(
        f"Sufficient claimed:     "
        f"{sufficient_claimed}/{total}"
    )

    print(
        f"Zero-evidence outputs:   "
        f"{zero_evidence}/{total}"
    )

    print(
        f"Scored runs:            "
        f"{len(scored)}/{total}"
    )

    print(
        f"Event-level misses:      "
        f"{event_level_misses}/{len(scored)}"
    )

    if not scored:
        print("\nNo scored query results.")
        return summary

    print()

    print(
        f"Mean precision:          "
        f"{mean_precision:.3f}"
    )

    print(
        f"Mean recall:             "
        f"{mean_recall:.3f}"
    )

    print(
        f"Mean IoU:                "
        f"{mean_iou:.3f}"
    )

    print(
        f"Mean segment recall:     "
        f"{mean_segment_recall:.3f}"
    )

    print(
        f"Mean video retained:     "
        f"{mean_video_retained:.1f}%"
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

        gt_intervals = (
            get_ground_truth_intervals(
                annotation,
                query
            )
        )
        
        relevant_segments = (
          query["ground_truth"]
          ["evidence"]
          ["relevant_segments"]
)

        query_result = {
            "query_id":
                query_id,

            "query":
                query["query"],

            "ground_truth": {
                "relevant_segments":
                    query["ground_truth"]
                    ["evidence"]
                    ["relevant_segments"],

                "intervals":
                    gt_intervals,
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
        # Score model response
        #
        # Scoring policy:
        #
        # Every successfully executed query with known ground truth
        # contributes to task-performance metrics.
        #
        # Valid usable evidence:
        #     Score the selected intervals normally.
        #
        # Parse/schema/semantic failure with no usable evidence:
        #     Assign zero task-performance scores.
        #
        # Container/model execution failure:
        #     Leave metrics as None because no model prediction was
        #     successfully produced.
        # --------------------------------------------------------------

        can_score_evidence = (
            parsed["parse_success"]
            and isinstance(
                parsed["parsed"],
                dict
            )
            and isinstance(
                parsed["parsed"].get("evidence"),
                list
            )
        )

        usable_evidence = False

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
                    item["start"],
                    item["end"]
                ]
                for item in evidence_items
            ]

            metrics = calculate_metrics(
                gt_intervals,
                selected,
                annotation["duration"]
            )

        else:

            # The model executed successfully but did not produce a
            # usable evidence prediction. This is a task failure and
            # therefore receives zero performance scores rather than
            # being excluded from the aggregate.
            metrics = make_zero_metrics(
                gt_intervals,
                relevant_segments
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