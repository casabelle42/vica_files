#!/usr/bin/env python3

import argparse
import json
import os
from statistics import mean


DEFAULT_OUTPUT_DIR = (
    "/home/las_edge_account/LAS-VICA/"
    "results/experiment_c/scored"
)


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


def safe_mean(values):

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return mean(values)


def bool_to_float(value):

    if value is True:
        return 1.0

    if value is False:
        return 0.0

    return None


def index_queries(data):

    return {
        query["query_id"]: query
        for query in data["queries"]
    }


def get_condition_order(
    annotation,
    experiment_c
):

    config = annotation.get(
        "experiment_c_config",
        {}
    )

    condition_order = config.get(
        "condition_order"
    )

    if condition_order:
        return condition_order

    config = experiment_c.get(
        "configuration",
        {}
    )

    condition_order = config.get(
        "condition_order"
    )

    if condition_order:
        return condition_order

    raise ValueError(
        "Could not determine Experiment C "
        "condition order."
    )


def validate_inputs(
    annotation,
    human_scores,
    experiment_c,
    condition_order
):

    video_ids = {
        annotation.get("video_id"),
        human_scores.get("video_id"),
        experiment_c.get("video_id")
    }

    if len(video_ids) != 1:
        raise ValueError(
            "Video IDs do not match: "
            f"{video_ids}"
        )

    score_model = human_scores.get(
        "model"
    )

    result_model = experiment_c.get(
        "model"
    )

    if (
        score_model is not None
        and result_model is not None
        and score_model != result_model
    ):
        raise ValueError(
            "Model mismatch between human "
            "scores and Experiment C results: "
            f"{score_model} != {result_model}"
        )

    annotation_queries = index_queries(
        annotation
    )

    human_queries = index_queries(
        human_scores
    )

    result_queries = index_queries(
        experiment_c
    )

    for query_id in annotation_queries:

        if query_id not in human_queries:
            raise ValueError(
                f"{query_id}: missing from "
                "human scores"
            )

        if query_id not in result_queries:
            raise ValueError(
                f"{query_id}: missing from "
                "Experiment C results"
            )

        human_query = human_queries[
            query_id
        ]

        result_query = result_queries[
            query_id
        ]

        result_conditions = (
            result_query.get(
                "conditions",
                {}
            )
        )

        for condition_name in condition_order:

            if condition_name not in human_query:
                raise ValueError(
                    f"{query_id}: missing human "
                    f"score condition "
                    f"{condition_name}"
                )

            if condition_name not in result_conditions:
                raise ValueError(
                    f"{query_id}: missing "
                    f"Experiment C result "
                    f"condition {condition_name}"
                )


def score_condition(
    human_condition,
    result_condition
):

    answer_correct = (
        human_condition.get(
            "answer_correct"
        )
    )

    temporal_correct = (
        human_condition.get(
            "temporal_order_correct"
        )
    )

    attribution_correct = (
        human_condition.get(
            "event_attribution_correct"
        )
    )

    unsupported_claims = (
        human_condition.get(
            "unsupported_claims",
            []
        )
    )

    if unsupported_claims is None:
        unsupported_claims = []

    if not isinstance(
        unsupported_claims,
        list
    ):
        raise ValueError(
            "unsupported_claims must "
            "be a list"
        )

    execution_success = (
        result_condition.get(
            "execution_success",
            False
        )
    )

    evidence_budget = (
        result_condition.get(
            "evidence_budget",
            {}
        )
    )

    return {
        "execution_success":
            execution_success,

        "answer_correct":
            answer_correct,

        "temporal_order_correct":
            temporal_correct,

        "event_attribution_correct":
            attribution_correct,

        "unsupported_claim_count":
            len(unsupported_claims),

        "unsupported_claims":
            unsupported_claims,

        "evidence_budget":
            evidence_budget,

        "response":
            result_condition.get(
                "response"
            )
    }


def summarize_condition(
    condition_name,
    scored_queries
):

    condition_scores = [
        query["conditions"][
            condition_name
        ]
        for query in scored_queries
    ]

    answer_values = [
        bool_to_float(
            item["answer_correct"]
        )
        for item in condition_scores
    ]

    temporal_values = [
        bool_to_float(
            item[
                "temporal_order_correct"
            ]
        )
        for item in condition_scores
    ]

    attribution_values = [
        bool_to_float(
            item[
                "event_attribution_correct"
            ]
        )
        for item in condition_scores
    ]

    execution_values = [
        1.0
        if item[
            "execution_success"
        ]
        else 0.0
        for item in condition_scores
    ]

    unsupported_counts = [
        item[
            "unsupported_claim_count"
        ]
        for item in condition_scores
    ]

    requested_frame_counts = [
        item[
            "evidence_budget"
        ].get(
            "requested_frame_count"
        )
        for item in condition_scores
    ]

    temporal_spans = [
        item[
            "evidence_budget"
        ].get(
            "temporal_span_seconds"
        )
        for item in condition_scores
    ]

    evidence_durations = [
        item[
            "evidence_budget"
        ].get(
            "evidence_duration_seconds"
        )
        for item in condition_scores
    ]

    return {
        "condition":
            condition_name,

        "execution_success_rate":
            safe_mean(
                execution_values
            ),

        "answer_accuracy":
            safe_mean(
                answer_values
            ),

        "temporal_order_accuracy":
            safe_mean(
                temporal_values
            ),

        "event_attribution_accuracy":
            safe_mean(
                attribution_values
            ),

        "unsupported_claim_count":
            sum(
                unsupported_counts
            ),

        "mean_unsupported_claims":
            safe_mean(
                unsupported_counts
            ),

        "mean_requested_frame_count":
            safe_mean(
                requested_frame_counts
            ),

        "mean_temporal_span_seconds":
            safe_mean(
                temporal_spans
            ),

        "mean_evidence_duration_seconds":
            safe_mean(
                evidence_durations
            ),

        "answer_count":
            len([
                value
                for value in answer_values
                if value is not None
            ]),

        "temporal_order_count":
            len([
                value
                for value in temporal_values
                if value is not None
            ]),

        "event_attribution_count":
            len([
                value
                for value in attribution_values
                if value is not None
            ])
    }


def find_query_minimum_condition(
    query_result,
    condition_order
):

    for index, condition_name in enumerate(
        condition_order
    ):

        condition = query_result[
            "conditions"
        ][
            condition_name
        ]

        if (
            condition[
                "execution_success"
            ]
            and
            condition[
                "answer_correct"
            ] is True
        ):
            return {
                "condition":
                    condition_name,

                "condition_index":
                    index,

                "evidence_budget":
                    condition[
                        "evidence_budget"
                    ]
            }

    return None


def find_threshold_condition(
    condition_summaries,
    condition_order,
    threshold
):

    for index, condition_name in enumerate(
        condition_order
    ):

        summary = condition_summaries[
            condition_name
        ]

        accuracy = summary[
            "answer_accuracy"
        ]

        if (
            accuracy is not None
            and accuracy >= threshold
        ):
            return {
                "condition":
                    condition_name,

                "condition_index":
                    index,

                "answer_accuracy":
                    accuracy,

                "threshold":
                    threshold
            }

    return None


def format_metric(value):

    if value is None:
        return "N/A"

    return f"{value:.3f}"


def format_budget(value):

    if value is None:
        return "N/A"

    return f"{value:.2f}"


def print_query_results(
    scored_queries,
    condition_order
):

    for query in scored_queries:

        print()
        print("=" * 78)
        print(
            query["query_id"]
        )
        print("=" * 78)

        print(
            f"{'Condition':<18}"
            f"{'Answer':>10}"
            f"{'Temporal':>12}"
            f"{'Attribution':>14}"
            f"{'Unsupported':>14}"
        )

        print("-" * 78)

        for condition_name in condition_order:

            condition = query[
                "conditions"
            ][
                condition_name
            ]

            answer = (
                "True"
                if condition[
                    "answer_correct"
                ] is True
                else
                "False"
                if condition[
                    "answer_correct"
                ] is False
                else
                "N/A"
            )

            temporal = (
                "True"
                if condition[
                    "temporal_order_correct"
                ] is True
                else
                "False"
                if condition[
                    "temporal_order_correct"
                ] is False
                else
                "N/A"
            )

            attribution = (
                "True"
                if condition[
                    "event_attribution_correct"
                ] is True
                else
                "False"
                if condition[
                    "event_attribution_correct"
                ] is False
                else
                "N/A"
            )

            unsupported = (
                condition[
                    "unsupported_claim_count"
                ]
            )

            print(
                f"{condition_name:<18}"
                f"{answer:>10}"
                f"{temporal:>12}"
                f"{attribution:>14}"
                f"{unsupported:>14}"
            )

        minimum = query.get(
            "minimum_correct_condition"
        )

        print()

        if minimum is None:

            print(
                "Minimum correct condition: "
                "none"
            )

        else:

            print(
                "Minimum correct condition: "
                f"{minimum['condition']}"
            )


def print_summary(
    results,
    condition_order
):

    print()
    print("=" * 90)
    print("Experiment C Scoring Summary")
    print("=" * 90)

    print(
        f"Model:  "
        f"{results['model_display_name']}"
    )

    print(
        f"Video:  "
        f"{results['video_id']}"
    )

    print()

    print(
        f"{'Condition':<18}"
        f"{'Answer':>10}"
        f"{'Temporal':>12}"
        f"{'Attrib.':>12}"
        f"{'Unsup.':>10}"
        f"{'Frames':>10}"
        f"{'Duration':>12}"
    )

    print("-" * 90)

    summaries = results[
        "condition_summaries"
    ]

    for condition_name in condition_order:

        summary = summaries[
            condition_name
        ]

        print(
            f"{condition_name:<18}"
            f"{format_metric(summary['answer_accuracy']):>10}"
            f"{format_metric(summary['temporal_order_accuracy']):>12}"
            f"{format_metric(summary['event_attribution_accuracy']):>12}"
            f"{summary['unsupported_claim_count']:>10}"
            f"{format_budget(summary['mean_requested_frame_count']):>10}"
            f"{format_budget(summary['mean_evidence_duration_seconds']):>12}"
        )

    print()

    threshold_result = results.get(
        "minimum_threshold_condition"
    )

    threshold = results[
        "configuration"
    ][
        "acceptable_accuracy_threshold"
    ]

    print(
        "Acceptable accuracy threshold: "
        f"{threshold:.3f}"
    )

    if threshold_result is None:

        print(
            "Minimum condition reaching "
            "threshold: none"
        )

    else:

        print(
            "Minimum condition reaching "
            "threshold: "
            f"{threshold_result['condition']} "
            f"(accuracy="
            f"{threshold_result['answer_accuracy']:.3f})"
        )

    print()
    print(
        "Repeated-run consistency: "
        "not calculated "
        "(single run per condition)"
    )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Score Experiment C results "
            "using human annotations."
        )
    )

    parser.add_argument(
        "--annotation",
        required=True
    )

    parser.add_argument(
        "--human-scores",
        required=True
    )

    parser.add_argument(
        "--experiment-c",
        required=True
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR
    )

    parser.add_argument(
        "--acceptable-accuracy",
        type=float,
        default=0.80,
        help=(
            "Accuracy threshold used to "
            "identify the minimum evidence "
            "condition reaching acceptable "
            "performance. Default: 0.80"
        )
    )

    args = parser.parse_args()

    if not (
        0.0
        <= args.acceptable_accuracy
        <= 1.0
    ):
        raise ValueError(
            "--acceptable-accuracy must "
            "be between 0 and 1"
        )

    annotation = load_json(
        args.annotation
    )

    human_scores = load_json(
        args.human_scores
    )

    experiment_c = load_json(
        args.experiment_c
    )

    condition_order = get_condition_order(
        annotation,
        experiment_c
    )

    validate_inputs(
        annotation,
        human_scores,
        experiment_c,
        condition_order
    )

    annotation_queries = index_queries(
        annotation
    )

    human_queries = index_queries(
        human_scores
    )

    result_queries = index_queries(
        experiment_c
    )

    scored_queries = []

    for query_id in annotation_queries:

        annotation_query = (
            annotation_queries[
                query_id
            ]
        )

        human_query = (
            human_queries[
                query_id
            ]
        )

        result_query = (
            result_queries[
                query_id
            ]
        )

        scored_query = {
            "query_id":
                query_id,

            "query":
                annotation_query[
                    "query"
                ],

            "query_type":
                annotation_query.get(
                    "query_type"
                ),

            "conditions": {}
        }

        for condition_name in condition_order:

            human_condition = (
                human_query[
                    condition_name
                ]
            )

            result_condition = (
                result_query[
                    "conditions"
                ][
                    condition_name
                ]
            )

            scored_query[
                "conditions"
            ][
                condition_name
            ] = score_condition(
                human_condition,
                result_condition
            )

        scored_query[
            "minimum_correct_condition"
        ] = find_query_minimum_condition(
            scored_query,
            condition_order
        )

        scored_queries.append(
            scored_query
        )

    condition_summaries = {}

    for condition_name in condition_order:

        condition_summaries[
            condition_name
        ] = summarize_condition(
            condition_name,
            scored_queries
        )

    threshold_result = (
        find_threshold_condition(
            condition_summaries,
            condition_order,
            args.acceptable_accuracy
        )
    )

    results = {
        "experiment": "C",

        "video_id":
            annotation[
                "video_id"
            ],

        "model":
            experiment_c[
                "model"
            ],

        "model_display_name":
            experiment_c.get(
                "model_display_name",
                experiment_c[
                    "model"
                ]
            ),

        "configuration": {
            "condition_order":
                condition_order,

            "acceptable_accuracy_threshold":
                args.acceptable_accuracy
        },

        "queries":
            scored_queries,

        "condition_summaries":
            condition_summaries,

        "minimum_threshold_condition":
            threshold_result,

        "consistency": {
            "available": False,
            "reason": (
                "Only one run per "
                "query-condition pair."
            )
        }
    }

    print_query_results(
        scored_queries,
        condition_order
    )

    print_summary(
        results,
        condition_order
    )

    output_filename = (
        f"{annotation['video_id']}_"
        f"{experiment_c['model']}_"
        "experiment_c_scored.json"
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
    print(
        "Scored results saved to:"
    )
    print(
        output_path
    )


if __name__ == "__main__":
    main()