#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import subprocess

from datetime import datetime


# ======================================================================
# Configuration
# ======================================================================

PROJECT_ROOT = "/home/las_edge_account/LAS-VICA"
CONTAINER_PROJECT_ROOT = "/workspace"

DEFAULT_VIDEO_DIR = os.path.join(
    PROJECT_ROOT,
    "videos",
    "counterfactual_vids",
    "data"
)

DEFAULT_PROMPT = os.path.join(
    PROJECT_ROOT,
    "prompts",
    "experiment_c.txt"
)

DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "results",
    "experiment_c"
)


# ----------------------------------------------------------------------
# Global Experiment C condition order
#
# This is a fixed experimental rule and therefore does not need to be
# repeated in every annotation.
# ----------------------------------------------------------------------

CONDITION_ORDER = [
    "isolated_frame",
    "sparse_frames",
    "short_sequence",
    "full_relevant",
    "full_video",
]


MODEL_CONFIG = {

    "cosmos_reason2": {
        "display_name": "Cosmos-Reason2",
        "container": "cosmos-reason2",
        "script": (
            "/workspace/models/"
            "cosmos-reason2/"
            "cosmos-reason2_infer.py"
        ),
        "response_start":
            "=== Cosmos-Reason2 Response ===",
        "response_end":
            "=== End Response ===",
    },

    "cosmos3": {
        "display_name": "Cosmos3 Edge",
        "container": "cosmos3-local",
        "script": (
            "/workspace/models/"
            "cosmos3-edge/"
            "cosmos3_infer.py"
        ),
        "response_start":
            "=== Cosmos3 Edge Response ===",
        "response_end":
            "=== End Response ===",
    },

    # InternVideo 2.5 still needs to be implemented.
}


# ======================================================================
# File utilities
# ======================================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def load_text(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return f.read().strip()


def save_json(data, path):

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


# ======================================================================
# Path utilities
# ======================================================================

def host_to_container_path(path):

    absolute_path = os.path.abspath(
        path
    )

    project_root = os.path.abspath(
        PROJECT_ROOT
    )

    relative_path = os.path.relpath(
        absolute_path,
        project_root
    )

    if relative_path.startswith(".."):

        raise ValueError(
            "Path must be inside LAS-VICA project: "
            f"{absolute_path}"
        )

    return os.path.join(
        CONTAINER_PROJECT_ROOT,
        relative_path
    )


# ======================================================================
# Interval utilities
# ======================================================================

def merge_intervals(intervals):

    if not intervals:
        return []

    normalized = sorted(
        [
            [
                float(start),
                float(end)
            ]
            for start, end in intervals
        ],
        key=lambda x: x[0]
    )

    merged = [
        normalized[0]
    ]

    for start, end in normalized[1:]:

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
        for start, end
        in merge_intervals(intervals)
    )


def temporal_span_from_frames(
    frame_timestamps
):

    if not frame_timestamps:
        return 0.0

    if len(frame_timestamps) == 1:
        return 0.0

    return (
        max(frame_timestamps)
        - min(frame_timestamps)
    )


def temporal_span_from_intervals(
    intervals
):

    if not intervals:
        return 0.0

    merged = merge_intervals(
        intervals
    )

    return (
        merged[-1][1]
        - merged[0][0]
    )


# ======================================================================
# Evidence validation
# ======================================================================

def validate_frame_timestamps(
    timestamps,
    video_duration
):

    for timestamp in timestamps:

        if timestamp < 0:

            raise ValueError(
                "Frame timestamp cannot "
                f"be negative: {timestamp}"
            )

        if timestamp > video_duration:

            raise ValueError(
                "Frame timestamp exceeds "
                f"video duration: {timestamp}"
            )


def validate_intervals(
    intervals,
    video_duration
):

    for start, end in intervals:

        if start < 0:

            raise ValueError(
                "Interval start cannot "
                f"be negative: {start}"
            )

        if end < start:

            raise ValueError(
                "Interval end precedes "
                f"start: [{start}, {end}]"
            )

        if end > video_duration:

            raise ValueError(
                "Interval exceeds video "
                f"duration: [{start}, {end}]"
            )


# ======================================================================
# Prompt
# ======================================================================

def build_question(
    base_prompt,
    analyst_query
):

    return (
        f"{base_prompt.rstrip()}\n\n"
        f"Analyst query:\n"
        f"{analyst_query.strip()}"
    )


# ======================================================================
# Model response extraction
# ======================================================================

def extract_model_response(
    stdout,
    model_name
):

    config = MODEL_CONFIG[
        model_name
    ]

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

    match = pattern.search(
        stdout
    )

    if match:

        return match.group(1).strip()

    return stdout.strip()


# ======================================================================
# JSON response parsing
# ======================================================================

def strip_markdown_json_fence(text):

    text = text.strip()

    match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    if match:

        return match.group(1).strip()

    return text


def parse_json_response(text):
    """
    Experiment C uses the same answer contract as Experiment B:

        {
            "answer": "<natural-language answer>"
        }

    Structured scoring is performed separately by the automated
    answer evaluator.
    """

    if not text:

        return {
            "parse_success": False,
            "validation_success": False,
            "parsed": None,
            "error": "empty response",
        }

    cleaned = strip_markdown_json_fence(
        text
    )

    try:

        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError as exc:

        return {
            "parse_success": False,
            "validation_success": False,
            "parsed": None,
            "error": str(exc),
        }

    if not isinstance(
        parsed,
        dict
    ):

        return {
            "parse_success": True,
            "validation_success": False,
            "parsed": parsed,
            "error":
                "response JSON must be an object",
        }

    answer = parsed.get(
        "answer"
    )

    if not isinstance(
        answer,
        str
    ):

        return {
            "parse_success": True,
            "validation_success": False,
            "parsed": parsed,
            "error":
                "answer must be a string",
        }

    if not answer.strip():

        return {
            "parse_success": True,
            "validation_success": False,
            "parsed": parsed,
            "error":
                "answer must not be empty",
        }

    return {
        "parse_success": True,
        "validation_success": True,
        "parsed": parsed,
        "error": None,
    }


# ======================================================================
# Docker command
# ======================================================================

def build_command(
    model_name,
    video_path,
    question,
    sample_fps,
    evidence_type,
    frame_timestamps=None,
    evidence_intervals=None
):

    config = MODEL_CONFIG[
        model_name
    ]

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
        (
            f"{PROJECT_ROOT}:"
            f"{CONTAINER_PROJECT_ROOT}"
        ),

        "--entrypoint",
        "python3",

        config["container"],

        config["script"],

        "--video-path",
        video_path,

        "--sample-fps",
        str(sample_fps),

        "--question",
        question
    ]

    if evidence_type == "frames":

        timestamps_json = json.dumps(
            frame_timestamps,
            separators=(",", ":")
        )

        command.extend(
            [
                "--frame-timestamps",
                timestamps_json
            ]
        )

    elif evidence_type == "intervals":

        intervals_json = json.dumps(
            evidence_intervals,
            separators=(",", ":")
        )

        command.extend(
            [
                "--evidence-intervals",
                intervals_json
            ]
        )

    elif evidence_type == "full_video":

        pass

    else:

        raise ValueError(
            "Unsupported evidence type: "
            f"{evidence_type}"
        )

    return command


# ======================================================================
# Model execution
# ======================================================================

def run_model(
    model_name,
    video_path,
    question,
    sample_fps,
    evidence_type,
    frame_timestamps=None,
    evidence_intervals=None
):

    command = build_command(
        model_name=model_name,
        video_path=video_path,
        question=question,
        sample_fps=sample_fps,
        evidence_type=evidence_type,
        frame_timestamps=frame_timestamps,
        evidence_intervals=evidence_intervals
    )

    print(
        f"Running "
        f"{MODEL_CONFIG[model_name]['display_name']}..."
    )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if completed.returncode != 0:

        return {
            "execution_success": False,
            "return_code":
                completed.returncode,
            "raw_response": None,
            "parse_success": False,
            "validation_success": False,
            "validation_error":
                completed.stderr,
            "parsed_response": None,
            "stdout":
                completed.stdout,
            "stderr":
                completed.stderr,
            "condition_status":
                "execution_failure",
        }

    response_text = extract_model_response(
        completed.stdout,
        model_name
    )

    parsed = parse_json_response(
        response_text
    )

    return {
        "execution_success": True,

        "return_code":
            completed.returncode,

        "raw_response":
            response_text,

        "parse_success":
            parsed["parse_success"],

        "validation_success":
            parsed["validation_success"],

        "validation_error":
            parsed["error"],

        "parsed_response":
            parsed["parsed"],

        "stdout":
            completed.stdout,

        "stderr":
            completed.stderr,

        "condition_status":
            (
                "valid"
                if parsed["validation_success"]
                else "invalid_output"
            ),
    }


# ======================================================================
# Resolve Experiment C condition
# ======================================================================

def resolve_condition(
    condition_name,
    condition,
    query,
    annotation
):

    evidence_type = condition.get(
        "evidence_type"
    )

    video_duration = float(
        annotation["duration"]
    )

    # ------------------------------------------------------------------
    # Isolated / sparse frames
    # ------------------------------------------------------------------

    if evidence_type == "frames":

        frame_timestamps = [
            float(value)
            for value in condition.get(
                "timestamps",
                []
            )
        ]

        if not frame_timestamps:

            raise ValueError(
                f"{query['query_id']} "
                f"{condition_name}: "
                "no frame timestamps"
            )

        validate_frame_timestamps(
            frame_timestamps,
            video_duration
        )

        return {
            "resolved_evidence_type":
                "frames",

            "frame_timestamps":
                frame_timestamps,

            "evidence_intervals":
                None
        }

    # ------------------------------------------------------------------
    # Explicit short sequence
    # ------------------------------------------------------------------

    if evidence_type == "intervals":

        intervals = [
            [
                float(start),
                float(end)
            ]
            for start, end
            in condition.get(
                "intervals",
                []
            )
        ]

        if not intervals:

            raise ValueError(
                f"{query['query_id']} "
                f"{condition_name}: "
                "no intervals"
            )

        validate_intervals(
            intervals,
            video_duration
        )

        return {
            "resolved_evidence_type":
                "intervals",

            "frame_timestamps":
                None,

            "evidence_intervals":
                intervals
        }

    # ------------------------------------------------------------------
    # Full relevant evidence
    #
    # IMPORTANT:
    # Use finalized relevant_intervals directly.
    # Do not reconstruct these from relevant_segments.
    # ------------------------------------------------------------------

    if (
        evidence_type
        == "ground_truth_relevant"
    ):

        evidence = (
            query[
                "ground_truth"
            ][
                "evidence"
            ]
        )

        intervals = [
            [
                float(start),
                float(end)
            ]
            for start, end
            in evidence.get(
                "relevant_intervals",
                []
            )
        ]

        if not intervals:

            raise ValueError(
                f"{query['query_id']} "
                f"{condition_name}: "
                "no relevant_intervals"
            )

        validate_intervals(
            intervals,
            video_duration
        )

        return {
            "resolved_evidence_type":
                "intervals",

            "frame_timestamps":
                None,

            "evidence_intervals":
                intervals
        }

    # ------------------------------------------------------------------
    # Full video
    # ------------------------------------------------------------------

    if evidence_type == "full_video":

        return {
            "resolved_evidence_type":
                "full_video",

            "frame_timestamps":
                None,

            "evidence_intervals":
                None
        }

    raise ValueError(
        f"{query['query_id']} "
        f"{condition_name}: "
        "unsupported evidence_type "
        f"{evidence_type}"
    )


# ======================================================================
# Evidence budget
# ======================================================================

def calculate_requested_budget(
    resolved,
    video_duration
):

    evidence_type = resolved[
        "resolved_evidence_type"
    ]

    if evidence_type == "frames":

        timestamps = resolved[
            "frame_timestamps"
        ]

        return {
            "requested_frame_count":
                len(timestamps),

            "temporal_span_seconds":
                temporal_span_from_frames(
                    timestamps
                ),

            "evidence_duration_seconds":
                0.0,

            "percentage_video_duration":
                0.0,
        }

    if evidence_type == "intervals":

        intervals = resolved[
            "evidence_intervals"
        ]

        duration = interval_duration(
            intervals
        )

        percentage = (
            100.0
            * duration
            / float(video_duration)
            if video_duration > 0
            else 0.0
        )

        return {
            "requested_frame_count":
                None,

            "temporal_span_seconds":
                temporal_span_from_intervals(
                    intervals
                ),

            "evidence_duration_seconds":
                duration,

            "percentage_video_duration":
                percentage,
        }

    if evidence_type == "full_video":

        return {
            "requested_frame_count":
                None,

            "temporal_span_seconds":
                float(video_duration),

            "evidence_duration_seconds":
                float(video_duration),

            "percentage_video_duration":
                100.0,
        }

    raise ValueError(
        f"Unsupported evidence type: "
        f"{evidence_type}"
    )


# ======================================================================
# Console helpers
# ======================================================================

def print_condition_header(
    condition_name,
    resolved
):

    print()
    print(
        f"--- {condition_name} ---"
    )

    evidence_type = resolved[
        "resolved_evidence_type"
    ]

    print(
        f"Evidence type: "
        f"{evidence_type}"
    )

    if evidence_type == "frames":

        print(
            "Frame timestamps: "
            f"{resolved['frame_timestamps']}"
        )

    elif evidence_type == "intervals":

        print(
            "Evidence intervals: "
            f"{resolved['evidence_intervals']}"
        )

    elif evidence_type == "full_video":

        print(
            "Evidence: full video"
        )


def print_model_result(
    model_result
):

    if model_result.get(
        "parsed_response"
    ):

        print(
            json.dumps(
                model_result[
                    "parsed_response"
                ],
                indent=2,
                ensure_ascii=False
            )
        )

    elif model_result.get(
        "raw_response"
    ):

        print(
            model_result[
                "raw_response"
            ]
        )

    else:

        print(
            "Status: "
            f"{model_result['condition_status']}"
        )


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run Experiment C temporal "
            "evidence evaluation."
        )
    )

    parser.add_argument(
        "--model",
        required=True,
        choices=MODEL_CONFIG.keys()
    )

    parser.add_argument(
        "--annotation",
        required=True
    )

    parser.add_argument(
        "--video",
        default=None
    )

    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0
    )

    parser.add_argument(
        "--prompt-file",
        default=DEFAULT_PROMPT
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR
    )

    parser.add_argument(
        "--query-id",
        default=None,
        help=(
            "Optional single query to run, "
            "for example Q3."
        )
    )

    parser.add_argument(
        "--condition",
        default=None,
        choices=CONDITION_ORDER,
        help=(
            "Optional single Experiment C "
            "condition to run."
        )
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load annotation and prompt
    # ------------------------------------------------------------------

    annotation = load_json(
        args.annotation
    )

    base_prompt = load_text(
        args.prompt_file
    )

    model_config = MODEL_CONFIG[
        args.model
    ]

    # ------------------------------------------------------------------
    # Resolve video
    # ------------------------------------------------------------------

    if args.video is None:

        host_video_path = os.path.join(
            DEFAULT_VIDEO_DIR,
            annotation["video_file"]
        )

    else:

        host_video_path = args.video

    if not os.path.isfile(
        host_video_path
    ):

        raise FileNotFoundError(
            f"Video not found: "
            f"{host_video_path}"
        )

    container_video_path = (
        host_to_container_path(
            host_video_path
        )
    )

    video_duration = float(
        annotation["duration"]
    )

    # ------------------------------------------------------------------
    # Result structure
    # ------------------------------------------------------------------

    results = {
        "experiment": "C",

        "model":
            args.model,

        "model_display_name":
            model_config[
                "display_name"
            ],

        "video_id":
            annotation[
                "video_id"
            ],

        "video_file":
            annotation[
                "video_file"
            ],

        "configuration": {
            "sample_fps":
                args.sample_fps,

            "prompt_file":
                os.path.relpath(
                    os.path.abspath(
                        args.prompt_file
                    ),
                    PROJECT_ROOT
                ),

            "condition_order":
                CONDITION_ORDER,

            "full_relevant_policy":
                "relevant_intervals",

            "answer_contract": {
                "answer":
                    "natural-language string"
            },

            "evaluation_policy":
                (
                    "Structured answer evaluation "
                    "is performed separately using "
                    "the same automated scorer as "
                    "Experiment B."
                ),
        },

        "queries": []
    }

    # ------------------------------------------------------------------
    # Select queries
    # ------------------------------------------------------------------

    queries = annotation[
        "queries"
    ]

    if args.query_id is not None:

        queries = [
            query
            for query in queries
            if query["query_id"]
            == args.query_id
        ]

        if not queries:

            raise ValueError(
                "Query not found: "
                f"{args.query_id}"
            )

    # ------------------------------------------------------------------
    # Run queries
    # ------------------------------------------------------------------

    for query_index, query in enumerate(
        queries,
        start=1
    ):

        query_id = query[
            "query_id"
        ]

        analyst_query = query[
            "query"
        ]

        question = build_question(
            base_prompt,
            analyst_query
        )

        print()
        print("=" * 60)
        print(
            f"Query {query_index}/"
            f"{len(queries)}: "
            f"{query_id}"
        )
        print("=" * 60)
        print(
            analyst_query
        )

        # --------------------------------------------------------------
        # Per-query C annotation
        # --------------------------------------------------------------

        experiment_c = query.get(
            "experiment_c"
        )

        if not experiment_c:

            raise ValueError(
                f"{query_id}: missing "
                "experiment_c"
            )

        conditions = experiment_c.get(
            "conditions",
            {}
        )

        # --------------------------------------------------------------
        # Preserve complete scoring ground truth
        # --------------------------------------------------------------

        ground_truth = query[
            "ground_truth"
        ]

        query_result = {
            "query_id":
                query_id,

            "query":
                analyst_query,

            "query_type":
                query.get(
                    "query_type"
                ),

            "ground_truth": {
                "answer":
                    ground_truth.get(
                        "answer"
                    ),

                "required_claims":
                    ground_truth.get(
                        "required_claims",
                        []
                    ),

                "supporting_claims":
                    ground_truth.get(
                        "supporting_claims",
                        []
                    ),

                "temporal_relations":
                    ground_truth.get(
                        "temporal_relations",
                        []
                    ),

                "evidence":
                    ground_truth.get(
                        "evidence",
                        {}
                    ),
            },

            "conditions": {}
        }

        # --------------------------------------------------------------
        # Select conditions
        # --------------------------------------------------------------

        if args.condition is not None:

            conditions_to_run = [
                args.condition
            ]

        else:

            conditions_to_run = (
                CONDITION_ORDER
            )

        # --------------------------------------------------------------
        # Run conditions
        # --------------------------------------------------------------

        for condition_name in (
            conditions_to_run
        ):

            if condition_name not in conditions:

                raise ValueError(
                    f"{query_id}: "
                    f"missing condition "
                    f"{condition_name}"
                )

            condition = conditions[
                condition_name
            ]

            resolved = resolve_condition(
                condition_name,
                condition,
                query,
                annotation
            )

            print_condition_header(
                condition_name,
                resolved
            )

            budget = (
                calculate_requested_budget(
                    resolved,
                    video_duration
                )
            )

            model_result = run_model(
                model_name=args.model,

                video_path=(
                    container_video_path
                ),

                question=question,

                sample_fps=args.sample_fps,

                evidence_type=(
                    resolved[
                        "resolved_evidence_type"
                    ]
                ),

                frame_timestamps=(
                    resolved[
                        "frame_timestamps"
                    ]
                ),

                evidence_intervals=(
                    resolved[
                        "evidence_intervals"
                    ]
                )
            )

            print()

            print_model_result(
                model_result
            )

            query_result[
                "conditions"
            ][
                condition_name
            ] = {

                "annotation_evidence_type":
                    condition[
                        "evidence_type"
                    ],

                "resolved_evidence_type":
                    resolved[
                        "resolved_evidence_type"
                    ],

                "frame_timestamps":
                    resolved[
                        "frame_timestamps"
                    ],

                "evidence_intervals":
                    resolved[
                        "evidence_intervals"
                    ],

                "evidence_budget":
                    budget,

                "execution_success":
                    model_result[
                        "execution_success"
                    ],

                "return_code":
                    model_result[
                        "return_code"
                    ],

                "raw_response":
                    model_result[
                        "raw_response"
                    ],

                "parse_success":
                    model_result[
                        "parse_success"
                    ],

                "validation_success":
                    model_result[
                        "validation_success"
                    ],

                "validation_error":
                    model_result[
                        "validation_error"
                    ],

                "parsed_response":
                    model_result[
                        "parsed_response"
                    ],

                "condition_status":
                    model_result[
                        "condition_status"
                    ],

                "stdout":
                    model_result[
                        "stdout"
                    ],

                "stderr":
                    model_result[
                        "stderr"
                    ]
            }

        results[
            "queries"
        ].append(
            query_result
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    total_conditions = sum(
        len(query["conditions"])
        for query in results["queries"]
    )

    valid_conditions = sum(
        1
        for query in results["queries"]
        for condition in query[
            "conditions"
        ].values()
        if condition[
            "condition_status"
        ] == "valid"
    )

    execution_failures = sum(
        1
        for query in results["queries"]
        for condition in query[
            "conditions"
        ].values()
        if condition[
            "condition_status"
        ] == "execution_failure"
    )

    invalid_outputs = sum(
        1
        for query in results["queries"]
        for condition in query[
            "conditions"
        ].values()
        if condition[
            "condition_status"
        ] == "invalid_output"
    )

    results["summary"] = {
        "total_queries":
            len(results["queries"]),

        "total_conditions":
            total_conditions,

        "valid_conditions":
            valid_conditions,

        "execution_failures":
            execution_failures,

        "invalid_outputs":
            invalid_outputs,
    }

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_filename = (
        f"{annotation['video_id']}_"
        f"{args.model}_"
        f"{timestamp}.json"
    )

    output_path = os.path.join(
        args.output_dir,
        output_filename
    )

    save_json(
        results,
        output_path
    )

    # ------------------------------------------------------------------
    # Final console output
    # ------------------------------------------------------------------

    print()
    print("=" * 60)
    print("Experiment C Complete")
    print("=" * 60)

    print(
        f"Model:      "
        f"{model_config['display_name']}"
    )

    print(
        f"Video:      "
        f"{annotation['video_id']}"
    )

    print(
        f"Queries:    "
        f"{len(results['queries'])}"
    )

    print(
        f"Conditions: "
        f"{total_conditions}"
    )

    print(
        f"Valid:      "
        f"{valid_conditions}"
    )

    print(
        f"Invalid:    "
        f"{invalid_outputs}"
    )

    print(
        f"Failures:   "
        f"{execution_failures}"
    )

    print()
    print(
        "Results saved to:"
    )
    print(
        output_path
    )


if __name__ == "__main__":
    main()
