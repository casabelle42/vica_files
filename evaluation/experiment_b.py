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

MODEL_CONFIGS = {

    "cosmos_reason2": {
        "display_name": "Cosmos-Reason2",
        "docker_image": "cosmos-reason2",
        "script": (
            "/workspace/models/cosmos-reason2/"
            "cosmos-reason2_infer.py"
        ),
    },
        
    "cosmos3": {
        "display_name": "Cosmos3 Edge",
        "docker_image": "cosmos3-local",
        "script": ("/workspace/models/cosmos3-edge/cosmos3_infer.py"
        ),
    },

    # still need to implement Internvideo 2.5
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


# ======================================================================
# Ground-truth evidence
# ======================================================================

def get_gt_intervals(
    annotation,
    query
):
    """
    Preliminary Experiment B ground-truth evidence.

    For now, use the annotation's relevant_segments.

    Later this function can prefer minimum_sufficient_intervals
    once those annotations are available.
    """

    evidence = (
        query["ground_truth"]
        ["evidence"]
    )

    # --------------------------------------------------------------
    # Future behavior
    # --------------------------------------------------------------

    minimum_intervals = evidence.get(
        "minimum_sufficient_intervals",
        []
    )

    if minimum_intervals:

        return (
            minimum_intervals,
            "minimum_sufficient_intervals"
        )

    # --------------------------------------------------------------
    # Preliminary behavior
    # --------------------------------------------------------------

    relevant_segments = evidence.get(
        "relevant_segments",
        []
    )

    intervals = []

    for segment_index in relevant_segments:

        start, end = annotation[
            "timestamps"
        ][segment_index]

        intervals.append(
            [
                float(start),
                float(end)
            ]
        )

    return (
        intervals,
        "relevant_segments"
    )


# ======================================================================
# Experiment A evidence
# ======================================================================

def find_experiment_a_query(
    experiment_a,
    query_id
):

    for query_result in experiment_a.get(
        "queries",
        []
    ):

        if (
            query_result.get("query_id")
            == query_id
        ):
            return query_result

    return None


def get_a_intervals(
    experiment_a,
    query_id
):
    """
    Extract the intervals selected by Experiment A.

    Returns:
        intervals
        source_status
    """

    query_result = find_experiment_a_query(
        experiment_a,
        query_id
    )

    if query_result is None:

        return [], "missing_query"

    if not query_result.get(
        "execution_success",
        False
    ):

        return [], "execution_failure"

    parsed = query_result.get(
        "parsed_response"
    )

    if not isinstance(
        parsed,
        dict
    ):

        return [], "invalid_response"

    evidence = parsed.get(
        "evidence"
    )

    if not isinstance(
        evidence,
        list
    ):

        return [], "no_usable_evidence"

    intervals = []

    for item in evidence:

        if not isinstance(
            item,
            dict
        ):
            continue

        start = item.get("start")
        end = item.get("end")

        if not isinstance(
            start,
            (int, float)
        ):
            continue

        if not isinstance(
            end,
            (int, float)
        ):
            continue

        if end < start:
            continue

        intervals.append(
            [
                float(start),
                float(end)
            ]
        )

    if not intervals:

        return [], "no_usable_evidence"

    return intervals, "valid"


# ======================================================================
# Prompt
# ======================================================================

def build_question(
    base_prompt,
    analyst_query
):

    return (
        f"{base_prompt}\n\n"
        f"Analyst query: "
        f"{analyst_query}"
    )


# ======================================================================
# Model execution
# ======================================================================

def run_cosmos_reason2(
    video_path,
    question,
    evidence_intervals,
    sample_fps
):

    intervals_json = json.dumps(
        evidence_intervals,
        separators=(",", ":")
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
        (
            "/home/las_edge_account/"
            "LAS-VICA:/workspace"
        ),

        "--entrypoint",
        "python3",

        "cosmos-reason2",

        (
            "/workspace/models/"
            "cosmos-reason2/"
            "cosmos-reason2_infer.py"
        ),

        "--video-path",
        video_path,

        "--sample-fps",
        str(sample_fps),

        "--evidence-intervals",
        intervals_json,

        "--question",
        question,
    ]

    print(
        f"Running Cosmos-Reason2 "
        f"with {len(evidence_intervals)} "
        f"evidence interval(s)..."
    )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    return {
        "execution_success":
            completed.returncode == 0,

        "return_code":
            completed.returncode,

        "stdout":
            completed.stdout,

        "stderr":
            completed.stderr,
    }

def run_cosmos3(
    video_path,
    question,
    evidence_intervals,
    sample_fps
):

    intervals_json = json.dumps(
        evidence_intervals,
        separators=(",", ":")
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
        (
            "/home/las_edge_account/"
            "LAS-VICA:/workspace"
        ),

        "--entrypoint",
        "python3",

        "cosmos3-local",

        (
            "/workspace/models/"
            "cosmos3-edge/"
            "cosmos3_infer.py"
        ),

        "--video-path",
        video_path,

        "--sample-fps",
        str(sample_fps),

        "--evidence-intervals",
        intervals_json,

        "--question",
        question,
    ]

    print(
        f"Running Cosmos3 Edge "
        f"with {len(evidence_intervals)} "
        f"evidence interval(s)..."
    )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    return {
        "execution_success":
            completed.returncode == 0,

        "return_code":
            completed.returncode,

        "stdout":
            completed.stdout,

        "stderr":
            completed.stderr,
    }
    
def run_model(
    model_name,
    video_path,
    question,
    evidence_intervals,
    sample_fps
):

    if model_name == "cosmos_reason2":

        return run_cosmos_reason2(
            video_path,
            question,
            evidence_intervals,
            sample_fps
        )

    elif model_name == "cosmos3":

        return run_cosmos3(
            video_path,
            question,
            evidence_intervals,
            sample_fps
        )

    raise ValueError(
        f"Unsupported model: {model_name}"
    )


# ======================================================================
# Extract model response
# ======================================================================

def extract_response_text(stdout):

    start_marker = (
        "=== Cosmos-Reason2 Response ==="
    )

    end_marker = (
        "=== End Response ==="
    )

    if start_marker not in stdout:

        return stdout.strip()

    response = stdout.split(
        start_marker,
        1
    )[1]

    if end_marker in response:

        response = response.split(
            end_marker,
            1
        )[0]

    return response.strip()


# ======================================================================
# JSON parsing
# ======================================================================

def parse_json_response(text):

    if not text:

        return {
            "parse_success": False,
            "parsed": None,
            "error": "empty response",
        }

    cleaned = text.strip()

    # Remove Markdown fences if present.

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    try:

        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError as e:

        return {
            "parse_success": False,
            "parsed": None,
            "error": str(e),
        }

    if not isinstance(
        parsed,
        dict
    ):

        return {
            "parse_success": False,
            "parsed": parsed,
            "error": (
                "response JSON must be an object"
            ),
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
            "error": (
                "answer must be a string"
            ),
        }

    return {
        "parse_success": True,
        "validation_success": True,
        "parsed": parsed,
        "error": None,
    }


# ======================================================================
# Run one B condition
# ======================================================================

def run_condition(
    model_name,
    video_path,
    question,
    intervals,
    sample_fps,
    evidence_source
):

    result = {
        "evidence_source":
            evidence_source,

        "evidence_intervals":
            intervals,
    }

    # --------------------------------------------------------------
    # No evidence selected
    #
    # Do not run the model with an empty frame set.
    # Preserve this as an Experiment-A evidence failure.
    # --------------------------------------------------------------

    if not intervals:

        result.update({
            "execution_success": None,
            "return_code": None,
            "raw_response": None,
            "parse_success": None,
            "validation_success": None,
            "validation_error": None,
            "parsed_response": None,
            "condition_status":
                "no_evidence_available",
        })

        return result

    # --------------------------------------------------------------
    # Run model
    # --------------------------------------------------------------

    execution = run_model(
        model_name,
        video_path,
        question,
        intervals,
        sample_fps
    )

    result[
        "execution_success"
    ] = execution[
        "execution_success"
    ]

    result[
        "return_code"
    ] = execution[
        "return_code"
    ]

    if not execution[
        "execution_success"
    ]:

        result.update({
            "raw_response":
                None,

            "parse_success":
                False,

            "validation_success":
                False,

            "validation_error":
                execution["stderr"],

            "parsed_response":
                None,

            "condition_status":
                "execution_failure",
        })

        return result

    # --------------------------------------------------------------
    # Extract response
    # --------------------------------------------------------------

    response_text = extract_response_text(
        execution["stdout"]
    )

    result[
        "raw_response"
    ] = response_text

    parsed = parse_json_response(
        response_text
    )

    result[
        "parse_success"
    ] = parsed.get(
        "parse_success",
        False
    )

    result[
        "validation_success"
    ] = parsed.get(
        "validation_success",
        False
    )

    result[
        "validation_error"
    ] = parsed.get(
        "error"
    )

    result[
        "parsed_response"
    ] = parsed.get(
        "parsed"
    )

    if result[
        "validation_success"
    ]:

        result[
            "condition_status"
        ] = "valid"

    else:

        result[
            "condition_status"
        ] = "invalid_output"

    return result


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Experiment B: answer analyst queries "
            "from selected video evidence"
        )
    )

    parser.add_argument(
        "--annotation",
        required=True,
        help="Annotation JSON"
    )

    parser.add_argument(
        "--experiment-a",
        required=True,
        help=(
            "Experiment A result JSON used "
            "for the model-selected condition"
        )
    )

    parser.add_argument(
        "--model",
        required=True,
        choices=MODEL_CONFIGS.keys()
    )

    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0
    )

    parser.add_argument(
        "--prompt-file",
        default="prompts/experiment_b.txt"
    )

    parser.add_argument(
        "--results-dir",
        default="results/experiment_b"
    )

    args = parser.parse_args()

    # --------------------------------------------------------------
    # Load files
    # --------------------------------------------------------------

    annotation = load_json(
        args.annotation
    )

    experiment_a = load_json(
        args.experiment_a
    )

    base_prompt = load_text(
        args.prompt_file
    )

    model_config = MODEL_CONFIGS[
        args.model
    ]

    # --------------------------------------------------------------
    # Validate Experiment A source
    # --------------------------------------------------------------

    if (
        experiment_a.get("video_id")
        != annotation.get("video_id")
    ):

        raise ValueError(
            "Experiment A video_id does not "
            "match annotation video_id"
        )

    if (
        experiment_a.get("model")
        != args.model
    ):

        raise ValueError(
            "Experiment A model does not "
            "match --model"
        )

    # --------------------------------------------------------------
    # Video path
    # --------------------------------------------------------------

    video_file = annotation[
        "video_file"
    ]

    # This is the path visible INSIDE Docker.

    video_path = (
        "/workspace/videos/"
        "counterfactual_vids/"
        "data/"
        f"{video_file}"
    )

    # --------------------------------------------------------------
    # Result structure
    # --------------------------------------------------------------

    results = {
        "experiment": "B",

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
            video_file,

        "configuration": {
            "sample_fps":
                args.sample_fps,

            "prompt_file":
                args.prompt_file,

            "ground_truth_evidence_policy":
                (
                    "minimum_sufficient_intervals "
                    "if available, otherwise "
                    "relevant_segments"
                ),

            "experiment_a_source":
                os.path.abspath(
                    args.experiment_a
                ),
        },

        "queries": [],
    }

    queries = annotation[
        "queries"
    ]

    # --------------------------------------------------------------
    # Run queries
    # --------------------------------------------------------------

    for index, query in enumerate(
        queries,
        start=1
    ):

        query_id = query[
            "query_id"
        ]

        analyst_query = query[
            "query"
        ]

        print("\n")
        print("=" * 60)

        print(
            f"Query {index}/{len(queries)}: "
            f"{query_id}"
        )

        print("=" * 60)

        print(
            analyst_query
        )

        question = build_question(
            base_prompt,
            analyst_query
        )

        # ----------------------------------------------------------
        # Human-selected evidence
        # ----------------------------------------------------------

        (
            gt_intervals,
            gt_source
        ) = get_gt_intervals(
            annotation,
            query
        )

        # ----------------------------------------------------------
        # Experiment-A-selected evidence
        # ----------------------------------------------------------

        (
            a_intervals,
            a_status
        ) = get_a_intervals(
            experiment_a,
            query_id
        )

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
                    query[
                        "ground_truth"
                    ].get(
                        "answer"
                    ),

                "required_claims":
                    query[
                        "ground_truth"
                    ].get(
                        "required_claims",
                        []
                    ),

                "temporal_relations":
                    query[
                        "ground_truth"
                    ].get(
                        "temporal_relations",
                        []
                    ),
            },

            "conditions": {},
        }

        # ==========================================================
        # B-GT
        # ==========================================================

        print("\n--- B-GT: Human evidence ---")

        print(
            "Evidence:",
            gt_intervals
        )

        b_gt = run_condition(
            args.model,
            video_path,
            question,
            gt_intervals,
            args.sample_fps,
            gt_source
        )

        query_result[
            "conditions"
        ][
            "ground_truth_evidence"
        ] = b_gt

        if b_gt.get(
            "parsed_response"
        ):

            print(
                json.dumps(
                    b_gt[
                        "parsed_response"
                    ],
                    indent=2
                )
            )

        elif b_gt.get(
            "raw_response"
        ):

            print(
                b_gt[
                    "raw_response"
                ]
            )

        else:

            print(
                f"Status: "
                f"{b_gt['condition_status']}"
            )

        # ==========================================================
        # B-A
        # ==========================================================

        print(
            "\n--- B-A: "
            "Experiment A evidence ---"
        )

        print(
            "Evidence:",
            a_intervals
        )

        b_a = run_condition(
            args.model,
            video_path,
            question,
            a_intervals,
            args.sample_fps,
            (
                "experiment_a:"
                f"{a_status}"
            )
        )

        query_result[
            "conditions"
        ][
            "model_selected_evidence"
        ] = b_a

        if b_a.get(
            "parsed_response"
        ):

            print(
                json.dumps(
                    b_a[
                        "parsed_response"
                    ],
                    indent=2
                )
            )

        elif b_a.get(
            "raw_response"
        ):

            print(
                b_a[
                    "raw_response"
                ]
            )

        else:

            print(
                f"Status: "
                f"{b_a['condition_status']}"
            )

        results[
            "queries"
        ].append(
            query_result
        )

    # --------------------------------------------------------------
    # Save
    # --------------------------------------------------------------

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

    print("\n")
    print("=" * 60)
    print("Experiment B Complete")
    print("=" * 60)

    print(
        f"Model:   "
        f"{model_config['display_name']}"
    )

    print(
        f"Video:   "
        f"{annotation['video_id']}"
    )

    print(
        f"Queries: "
        f"{len(results['queries'])}"
    )

    print(
        f"\nResults saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()