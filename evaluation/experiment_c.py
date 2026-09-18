#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess

from datetime import datetime


PROJECT_ROOT = "/home/las_edge_account/LAS-VICA"
CONTAINER_PROJECT_ROOT = "/workspace"

DEFAULT_ANNOTATION_DIR = os.path.join(
    PROJECT_ROOT,
    "videos",
    "counterfactual_vids",
    "annotations"
)

DEFAULT_VIDEO_DIR = os.path.join(
    PROJECT_ROOT,
    "videos",
    "counterfactual_vids",
    "data"
)

DEFAULT_OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "results",
    "experiment_c"
)


MODEL_CONFIG = {
    "cosmos_reason2": {
        "display_name": "Cosmos-Reason2",
        "container": "cosmos-reason2",
        "script": (
            "/workspace/models/"
            "cosmos-reason2/"
            "cosmos-reason2_infer.py"
        )
    },

    "cosmos3": {
        "display_name": "Cosmos3 Edge",
        "container": "cosmos3-local",
        "script": (
            "/workspace/models/"
            "cosmos3-edge/"
            "cosmos3_infer.py"
        )
    }
}


def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


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
            indent=2
        )


def host_to_container_path(path):

    absolute_path = os.path.abspath(path)

    if not absolute_path.startswith(
        PROJECT_ROOT
    ):
        raise ValueError(
            "Path must be inside LAS-VICA project: "
            f"{absolute_path}"
        )

    relative_path = os.path.relpath(
        absolute_path,
        PROJECT_ROOT
    )

    return os.path.join(
        CONTAINER_PROJECT_ROOT,
        relative_path
    )


def segments_to_intervals(
    segment_ids,
    timestamps
):

    intervals = []

    for segment_id in segment_ids:

        if (
            segment_id < 0
            or segment_id >= len(timestamps)
        ):
            raise ValueError(
                "Invalid segment ID: "
                f"{segment_id}"
            )

        start, end = timestamps[
            segment_id
        ]

        intervals.append(
            [
                float(start),
                float(end)
            ]
        )

    return intervals


def interval_duration(intervals):

    return sum(
        max(
            0.0,
            float(end) - float(start)
        )
        for start, end in intervals
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

    starts = [
        float(interval[0])
        for interval in intervals
    ]

    ends = [
        float(interval[1])
        for interval in intervals
    ]

    return max(ends) - min(starts)


def extract_model_response(stdout):

    patterns = [
        (
            r"=== Cosmos-Reason2 Response ==="
            r"\s*(.*?)\s*"
            r"=== End Response ==="
        ),
        (
            r"=== Cosmos3 Edge Response ==="
            r"\s*(.*?)\s*"
            r"=== End Response ==="
        )
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            stdout,
            flags=re.DOTALL
        )

        if match:

            return match.group(1).strip()

    return stdout.strip()


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

    response = None

    if completed.returncode == 0:

        response = extract_model_response(
            completed.stdout
        )

    return {
        "execution_success":
            completed.returncode == 0,

        "return_code":
            completed.returncode,

        "response":
            response,

        "stdout":
            completed.stdout,

        "stderr":
            completed.stderr
    }


def resolve_condition(
    condition_name,
    condition,
    query,
    annotation
):

    evidence_type = condition.get(
        "evidence_type"
    )

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

        return {
            "resolved_evidence_type":
                "frames",

            "frame_timestamps":
                frame_timestamps,

            "evidence_intervals":
                None
        }

    if evidence_type == "intervals":

        intervals = condition.get(
            "intervals",
            []
        )

        if not intervals:

            raise ValueError(
                f"{query['query_id']} "
                f"{condition_name}: "
                "no intervals"
            )

        intervals = [
            [
                float(start),
                float(end)
            ]
            for start, end in intervals
        ]

        return {
            "resolved_evidence_type":
                "intervals",

            "frame_timestamps":
                None,

            "evidence_intervals":
                intervals
        }

    if (
        evidence_type
        == "ground_truth_relevant"
    ):

        relevant_segments = (
            query[
                "ground_truth"
            ][
                "evidence"
            ].get(
                "relevant_segments",
                []
            )
        )

        intervals = segments_to_intervals(
            relevant_segments,
            annotation["timestamps"]
        )

        if not intervals:

            raise ValueError(
                f"{query['query_id']} "
                f"{condition_name}: "
                "no ground-truth relevant "
                "segments"
            )

        return {
            "resolved_evidence_type":
                "intervals",

            "frame_timestamps":
                None,

            "evidence_intervals":
                intervals
        }

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
                0.0
        }

    if evidence_type == "intervals":

        intervals = resolved[
            "evidence_intervals"
        ]

        return {
            "requested_frame_count":
                None,

            "temporal_span_seconds":
                temporal_span_from_intervals(
                    intervals
                ),

            "evidence_duration_seconds":
                interval_duration(
                    intervals
                )
        }

    if evidence_type == "full_video":

        return {
            "requested_frame_count":
                None,

            "temporal_span_seconds":
                float(video_duration),

            "evidence_duration_seconds":
                float(video_duration)
        }

    raise ValueError(
        f"Unsupported evidence type: "
        f"{evidence_type}"
    )


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
        help=(
            "Optional single Experiment C "
            "condition to run."
        )
    )

    args = parser.parse_args()

    annotation = load_json(
        args.annotation
    )

    model_config = MODEL_CONFIG[
        args.model
    ]

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

    c_config = annotation.get(
        "experiment_c_config"
    )

    if not c_config:

        raise ValueError(
            "Annotation is missing "
            "experiment_c_config"
        )

    condition_order = c_config.get(
        "condition_order",
        []
    )

    if not condition_order:

        raise ValueError(
            "experiment_c_config is "
            "missing condition_order"
        )

    if (
        args.condition is not None
        and args.condition
        not in condition_order
    ):
        raise ValueError(
            "Unknown condition: "
            f"{args.condition}"
        )

    results = {
        "experiment": "C",

        "model": args.model,

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

            "condition_order":
                condition_order
        },

        "queries": []
    }

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

    for query_index, query in enumerate(
        queries,
        start=1
    ):

        query_id = query[
            "query_id"
        ]

        question = query[
            "query"
        ]

        print()
        print("=" * 60)
        print(
            f"Query {query_index}/"
            f"{len(queries)}: "
            f"{query_id}"
        )
        print("=" * 60)
        print(question)

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

        query_result = {
            "query_id":
                query_id,

            "query":
                question,

            "query_type":
                query.get(
                    "query_type"
                ),

            "ground_truth_answer":
                query[
                    "ground_truth"
                ][
                    "answer"
                ],

            "conditions": {}
        }

        conditions_to_run = (
            condition_order
        )

        if args.condition is not None:

            conditions_to_run = [
                args.condition
            ]

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
                    annotation[
                        "duration"
                    ]
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

            if model_result[
                "execution_success"
            ]:

                print(
                    model_result[
                        "response"
                    ]
                )

            else:

                print(
                    "ERROR: model inference "
                    "failed."
                )

                if model_result[
                    "stderr"
                ]:
                    print(
                        model_result[
                            "stderr"
                        ]
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

                "response":
                    model_result[
                        "response"
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

    condition_count = sum(
        len(query["conditions"])
        for query in results["queries"]
    )

    print(
        f"Conditions: "
        f"{condition_count}"
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