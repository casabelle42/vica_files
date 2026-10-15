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

PROJECT_ROOT = "/media/las_edge_account/Database/LAS-VICA"

DEFAULT_PROMPT = os.path.join(
    PROJECT_ROOT,
    "prompts",
    "experiment_b.txt"
)

DEFAULT_RESULTS_DIR = os.path.join(
    PROJECT_ROOT,
    "results",
    "experiment_b"
)


MODEL_CONFIGS = {

    "cosmos_reason2": {
        "display_name": "Cosmos-Reason2",
        "docker_image": "cosmos-reason2",
        "script": (
            "/workspace/models/cosmos-reason2/"
            "cosmos-reason2_infer.py"
        ),
        "response_start": "=== Cosmos-Reason2 Response ===",
        "response_end": "=== End Response ===",
    },

    "cosmos3": {
        "display_name": "Cosmos3 Edge",
        "docker_image": "cosmos3-local",
        "script": (
            "/workspace/models/cosmos3-edge/"
            "cosmos3_infer.py"
        ),
        "response_start": "=== Cosmos3 Edge Response ===",
        "response_end": "=== End Response ===",
    },

    "internvideo2_5": {
        "display_name": "InternVideo2.5 Chat 8B",
        "docker_image": "internvideo2_5-local",
        "script": "/workspace/models/internvideo2_5/internvideo2_5_experiment_infer.py",
        "response_start": "=== InternVideo2.5 Response ===",
        "response_end": "=== End Response ===",
    },

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

def get_gt_intervals(query):
    """
    Select the human-annotated evidence used for B-GT.

    Policy:

        1. Use minimal_sufficient_intervals when available.
        2. Otherwise use relevant_intervals.

    relevant_segments are intentionally NOT used as a fallback because
    the finalized annotations now contain explicit temporal intervals.
    """

    evidence = (
        query["ground_truth"]
        ["evidence"]
    )

    minimal_intervals = evidence.get(
        "minimal_sufficient_intervals",
        []
    )

    if minimal_intervals:

        return (
            [
                [float(start), float(end)]
                for start, end in minimal_intervals
            ],
            "minimal_sufficient_intervals"
        )

    relevant_intervals = evidence.get(
        "relevant_intervals",
        []
    )

    if relevant_intervals:

        return (
            [
                [float(start), float(end)]
                for start, end in relevant_intervals
            ],
            "relevant_intervals"
        )

    return [], "no_ground_truth_evidence"


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
    query_id,
    video_duration
):
    """
    Extract usable intervals selected by Experiment A.

    B-A should use the prediction that Experiment A actually produced.
    However, structurally invalid or out-of-bounds evidence is not
    passed into the reasoning model.
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

    response_status = query_result.get(
        "response_status"
    )

    if response_status not in (
        None,
        "valid"
    ):

        return (
            [],
            f"experiment_a_{response_status}"
        )

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
            return [], "malformed_evidence"

        start = item.get("start")
        end = item.get("end")

        if not isinstance(
            start,
            (int, float)
        ):
            return [], "malformed_evidence"

        if not isinstance(
            end,
            (int, float)
        ):
            return [], "malformed_evidence"

        start = float(start)
        end = float(end)

        if start < 0:

            return [], "out_of_bounds_evidence"

        if end < start:

            return [], "malformed_evidence"

        if end > video_duration:

            return [], "out_of_bounds_evidence"

        intervals.append(
            [start, end]
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
        f"{base_prompt.rstrip()}\n\n"
        f"Analyst query:\n"
        f"{analyst_query.strip()}"
    )


# ======================================================================
# Model execution
# ======================================================================

def run_model(
    model_name,
    video_path,
    question,
    evidence_intervals,
    sample_fps
):

    if model_name not in MODEL_CONFIGS:

        raise ValueError(
            f"Unsupported model: {model_name}"
        )

    config = MODEL_CONFIGS[
        model_name
    ]

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
        f"{PROJECT_ROOT}:/workspace",

        "--entrypoint",
        "python3",

        config["docker_image"],

        config["script"],

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
        f"Running {config['display_name']} "
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


# ======================================================================
# Extract model response
# ======================================================================

def extract_response_text(
    stdout,
    model_name
):
    """
    Extract response text using the markers configured for
    the selected model.
    """

    config = MODEL_CONFIGS[
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
# JSON parsing
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
    Experiment B answering contract:

        {
            "answer": "<natural-language answer>"
        }

    The answer remains natural language. Structured ground-truth
    claims are NOT supplied to the answering model.
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

    if not answer.strip():

        return {
            "parse_success": True,
            "validation_success": False,
            "parsed": parsed,
            "error": (
                "answer must not be empty"
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
    # No evidence available
    #
    # Do not run the reasoning model with an empty evidence set.
    #
    # For B-A this preserves an upstream Experiment A failure.
    # For B-GT this indicates an annotation/evidence problem.
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
    # Extract and parse response
    # --------------------------------------------------------------

    response_text = extract_response_text(
        execution["stdout"],
        model_name
    )

    result[
        "raw_response"
    ] = response_text

    parsed = parse_json_response(
        response_text
    )

    result[
        "parse_success"
    ] = parsed[
        "parse_success"
    ]

    result[
        "validation_success"
    ] = parsed[
        "validation_success"
    ]

    result[
        "validation_error"
    ] = parsed[
        "error"
    ]

    result[
        "parsed_response"
    ] = parsed[
        "parsed"
    ]

    if parsed[
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
# Console output
# ======================================================================

def print_condition_result(result):

    if result.get(
        "parsed_response"
    ):

        print(
            json.dumps(
                result[
                    "parsed_response"
                ],
                indent=2,
                ensure_ascii=False
            )
        )

    elif result.get(
        "raw_response"
    ):

        print(
            result[
                "raw_response"
            ]
        )

    else:

        print(
            f"Status: "
            f"{result['condition_status']}"
        )


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Experiment B: answer analyst queries "
            "from human-selected and "
            "Experiment-A-selected evidence."
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
        default=DEFAULT_PROMPT
    )

    parser.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR
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
    # Video path visible inside Docker
    # --------------------------------------------------------------

    video_file = annotation[
        "video_file"
    ]

    video_path = (
        "/workspace/videos/"
        "counterfactual_vids/"
        "data/"
        f"{video_file}"
    )

    video_duration = float(
        annotation["duration"]
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
                os.path.relpath(
                    os.path.abspath(
                        args.prompt_file
                    ),
                    PROJECT_ROOT
                ),

            "ground_truth_evidence_policy":
                (
                    "minimal_sufficient_intervals "
                    "if available, otherwise "
                    "relevant_intervals"
                ),

            "experiment_a_source":
                os.path.abspath(
                    args.experiment_a
                ),

            "answer_contract":
                {
                    "answer":
                        "natural-language string"
                },

            "evaluation_policy":
                (
                    "Structured answer evaluation "
                    "is performed separately using "
                    "the finalized annotation claims "
                    "and temporal relations."
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
            query_id,
            video_duration
        )

        # ----------------------------------------------------------
        # Preserve complete evaluation ground truth
        # ----------------------------------------------------------

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

            "conditions": {},
        }

        # ==========================================================
        # B-GT
        # ==========================================================

        print(
            "\n--- B-GT: "
            "Human-selected evidence ---"
        )

        print(
            f"Evidence source: {gt_source}"
        )

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

        print_condition_result(
            b_gt
        )

        # ==========================================================
        # B-A
        # ==========================================================

        print(
            "\n--- B-A: "
            "Experiment A evidence ---"
        )

        print(
            f"Experiment A status: {a_status}"
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

        print_condition_result(
            b_a
        )

        results[
            "queries"
        ].append(
            query_result
        )

    # --------------------------------------------------------------
    # Condition summary
    # --------------------------------------------------------------

    gt_valid = sum(
        1
        for query in results["queries"]
        if (
            query["conditions"]
            ["ground_truth_evidence"]
            ["condition_status"]
            == "valid"
        )
    )

    a_valid = sum(
        1
        for query in results["queries"]
        if (
            query["conditions"]
            ["model_selected_evidence"]
            ["condition_status"]
            == "valid"
        )
    )

    a_no_evidence = sum(
        1
        for query in results["queries"]
        if (
            query["conditions"]
            ["model_selected_evidence"]
            ["condition_status"]
            == "no_evidence_available"
        )
    )

    results["summary"] = {
        "total_queries":
            len(results["queries"]),

        "ground_truth_evidence_valid_outputs":
            gt_valid,

        "model_selected_evidence_valid_outputs":
            a_valid,

        "model_selected_no_evidence":
            a_no_evidence,
    }

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

    # --------------------------------------------------------------
    # Final console summary
    # --------------------------------------------------------------

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
        f"B-GT valid outputs: "
        f"{gt_valid}/{len(results['queries'])}"
    )

    print(
        f"B-A valid outputs:  "
        f"{a_valid}/{len(results['queries'])}"
    )

    print(
        f"B-A no evidence:    "
        f"{a_no_evidence}/{len(results['queries'])}"
    )

    print(
        f"\nResults saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()
