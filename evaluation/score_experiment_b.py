#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
from datetime import datetime
from statistics import mean


# ======================================================================
# File utilities
# ======================================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


# ======================================================================
# Lookup utilities
# ======================================================================

def get_query_by_id(data, query_id):
    for query in data.get("queries", []):
        if query.get("query_id") == query_id:
            return query

    return None


def get_annotation_ids(query):
    """
    Return the valid claim/relation IDs defined by an annotation query.
    """

    ground_truth = query.get(
        "ground_truth",
        {}
    )

    required_ids = {
        claim["claim_id"]
        for claim in ground_truth.get(
            "required_claims",
            []
        )
        if "claim_id" in claim
    }

    supporting_ids = {
        claim["claim_id"]
        for claim in ground_truth.get(
            "supporting_claims",
            []
        )
        if "claim_id" in claim
    }

    relation_ids = {
        relation["relation_id"]
        for relation in ground_truth.get(
            "temporal_relations",
            []
        )
        if "relation_id" in relation
    }

    return (
        required_ids,
        supporting_ids,
        relation_ids
    )


# ======================================================================
# Validation
# ======================================================================

def validate_video_ids(
    annotation,
    human_scores,
    experiment_b
):
    annotation_id = annotation.get(
        "video_id"
    )

    human_id = human_scores.get(
        "video_id"
    )

    experiment_id = experiment_b.get(
        "video_id"
    )

    if human_id != annotation_id:
        raise ValueError(
            "Human-score video_id does not match "
            "annotation video_id: "
            f"{human_id!r} != {annotation_id!r}"
        )

    if experiment_id != annotation_id:
        raise ValueError(
            "Experiment B video_id does not match "
            "annotation video_id: "
            f"{experiment_id!r} != {annotation_id!r}"
        )


def validate_model(
    human_scores,
    experiment_b
):
    """
    If the human-score file contains a model field,
    make sure it matches the Experiment B result.
    """

    human_model = human_scores.get(
        "model"
    )

    experiment_model = experiment_b.get(
        "model"
    )

    if (
        human_model is not None
        and human_model != experiment_model
    ):
        raise ValueError(
            "Human-score model does not match "
            "Experiment B model: "
            f"{human_model!r} != "
            f"{experiment_model!r}"
        )


def validate_condition_scores(
    annotation_query,
    score_condition,
    query_id,
    condition_name
):
    """
    Make sure every scored claim/relation ID exists
    in the annotation and that no annotated IDs are
    accidentally omitted from the score file.
    """

    (
        required_ids,
        supporting_ids,
        relation_ids
    ) = get_annotation_ids(
        annotation_query
    )

    scored_required = set(
        score_condition.get(
            "required_claims",
            {}
        ).keys()
    )

    scored_supporting = set(
        score_condition.get(
            "supporting_claims",
            {}
        ).keys()
    )

    scored_relations = set(
        score_condition.get(
            "temporal_relations",
            {}
        ).keys()
    )

    # --------------------------------------------------------------
    # Unknown IDs
    # --------------------------------------------------------------

    unknown_required = (
        scored_required - required_ids
    )

    unknown_supporting = (
        scored_supporting - supporting_ids
    )

    unknown_relations = (
        scored_relations - relation_ids
    )

    if unknown_required:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "unknown required claim IDs: "
            f"{sorted(unknown_required)}"
        )

    if unknown_supporting:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "unknown supporting claim IDs: "
            f"{sorted(unknown_supporting)}"
        )

    if unknown_relations:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "unknown temporal relation IDs: "
            f"{sorted(unknown_relations)}"
        )

    # --------------------------------------------------------------
    # Missing IDs
    # --------------------------------------------------------------

    missing_required = (
        required_ids - scored_required
    )

    missing_supporting = (
        supporting_ids - scored_supporting
    )

    missing_relations = (
        relation_ids - scored_relations
    )

    if missing_required:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "missing required claim scores: "
            f"{sorted(missing_required)}"
        )

    if missing_supporting:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "missing supporting claim scores: "
            f"{sorted(missing_supporting)}"
        )

    if missing_relations:
        raise ValueError(
            f"{query_id} {condition_name}: "
            "missing temporal relation scores: "
            f"{sorted(missing_relations)}"
        )

    # --------------------------------------------------------------
    # Validate boolean values
    # --------------------------------------------------------------

    for category_name, values in [
        (
            "required_claims",
            score_condition.get(
                "required_claims",
                {}
            )
        ),
        (
            "supporting_claims",
            score_condition.get(
                "supporting_claims",
                {}
            )
        ),
        (
            "temporal_relations",
            score_condition.get(
                "temporal_relations",
                {}
            )
        ),
    ]:
        for item_id, value in values.items():
            if not isinstance(value, bool):
                raise ValueError(
                    f"{query_id} {condition_name}: "
                    f"{category_name}.{item_id} "
                    "must be true or false"
                )

    answer_correct = score_condition.get(
        "answer_correct"
    )

    if not isinstance(
        answer_correct,
        bool
    ):
        raise ValueError(
            f"{query_id} {condition_name}: "
            "answer_correct must be true or false"
        )

    unsupported = score_condition.get(
        "unsupported_claims",
        []
    )

    if not isinstance(
        unsupported,
        list
    ):
        raise ValueError(
            f"{query_id} {condition_name}: "
            "unsupported_claims must be a list"
        )


def validate_all(
    annotation,
    human_scores,
    experiment_b
):
    validate_video_ids(
        annotation,
        human_scores,
        experiment_b
    )

    validate_model(
        human_scores,
        experiment_b
    )

    annotation_queries = {
        q["query_id"]: q
        for q in annotation.get(
            "queries",
            []
        )
    }

    experiment_queries = {
        q["query_id"]: q
        for q in experiment_b.get(
            "queries",
            []
        )
    }

    human_queries = {
        q["query_id"]: q
        for q in human_scores.get(
            "queries",
            []
        )
    }

    annotation_ids = set(
        annotation_queries.keys()
    )

    experiment_ids = set(
        experiment_queries.keys()
    )

    human_ids = set(
        human_queries.keys()
    )

    if experiment_ids != annotation_ids:
        raise ValueError(
            "Experiment B query IDs do not match "
            "annotation query IDs.\n"
            f"Annotation: {sorted(annotation_ids)}\n"
            f"Experiment B: {sorted(experiment_ids)}"
        )

    if human_ids != annotation_ids:
        raise ValueError(
            "Human-score query IDs do not match "
            "annotation query IDs.\n"
            f"Annotation: {sorted(annotation_ids)}\n"
            f"Human scores: {sorted(human_ids)}"
        )

    for query_id in sorted(
        annotation_ids
    ):
        annotation_query = (
            annotation_queries[
                query_id
            ]
        )

        score_query = human_queries[
            query_id
        ]

        for condition_name in [
            "ground_truth_evidence",
            "model_selected_evidence"
        ]:
            if condition_name not in score_query:
                raise ValueError(
                    f"{query_id}: missing human "
                    f"score condition "
                    f"{condition_name}"
                )

            validate_condition_scores(
                annotation_query,
                score_query[
                    condition_name
                ],
                query_id,
                condition_name
            )


# ======================================================================
# Metric calculations
# ======================================================================

def boolean_recall(values):
    """
    Calculate recall from a dictionary such as:

        {
            "Q1_C1": true,
            "Q1_C2": false
        }

    Returns None when there are no items.
    """

    if not values:
        return None

    correct = sum(
        1
        for value in values.values()
        if value is True
    )

    total = len(values)

    return correct / total


def score_condition(
    human_condition,
    experiment_condition
):
    required = human_condition.get(
        "required_claims",
        {}
    )

    supporting = human_condition.get(
        "supporting_claims",
        {}
    )

    temporal = human_condition.get(
        "temporal_relations",
        {}
    )

    unsupported = human_condition.get(
        "unsupported_claims",
        []
    )

    required_found = sum(
        1
        for value in required.values()
        if value is True
    )

    supporting_found = sum(
        1
        for value in supporting.values()
        if value is True
    )

    temporal_correct = sum(
        1
        for value in temporal.values()
        if value is True
    )

    evidence_intervals = (
        experiment_condition.get(
            "evidence_intervals",
            []
        )
    )

    evidence_available = bool(
        evidence_intervals
    )

    return {
        "answer_correct":
            human_condition[
                "answer_correct"
            ],

        "evidence_available":
            evidence_available,

        "required_claims_found":
            required_found,

        "required_claims_total":
            len(required),

        "required_claim_recall":
            boolean_recall(
                required
            ),

        "supporting_claims_found":
            supporting_found,

        "supporting_claims_total":
            len(supporting),

        "supporting_claim_recall":
            boolean_recall(
                supporting
            ),

        "temporal_relations_correct":
            temporal_correct,

        "temporal_relations_total":
            len(temporal),

        "temporal_relation_accuracy":
            boolean_recall(
                temporal
            ),

        "unsupported_claim_count":
            len(unsupported),

        "unsupported_claims":
            unsupported,
    }


# ======================================================================
# Aggregate metrics
# ======================================================================

def mean_non_null(values):
    valid = [
        value
        for value in values
        if value is not None
    ]

    if not valid:
        return None

    return mean(valid)


def aggregate_condition(
    scored_queries,
    condition_name
):
    conditions = [
        query["conditions"][
            condition_name
        ]["metrics"]
        for query in scored_queries
    ]

    total = len(conditions)

    if total == 0:
        return {}

    correct = sum(
        1
        for condition in conditions
        if condition[
            "answer_correct"
        ]
    )

    evidence_available_count = sum(
        1
        for condition in conditions
        if condition[
            "evidence_available"
        ]
    )

    correct_with_evidence = sum(
        1
        for condition in conditions
        if (
            condition[
                "evidence_available"
            ]
            and
            condition[
                "answer_correct"
            ]
        )
    )

    if evidence_available_count:
        evidence_conditioned_accuracy = (
            correct_with_evidence
            / evidence_available_count
        )
    else:
        evidence_conditioned_accuracy = None

    unsupported_count = sum(
        condition[
            "unsupported_claim_count"
        ]
        for condition in conditions
    )

    return {
        "queries_total":
            total,

        "answers_correct":
            correct,

        "answer_accuracy":
            correct / total,

        "evidence_available_count":
            evidence_available_count,

        "evidence_availability_rate":
            evidence_available_count / total,

        "correct_with_evidence":
            correct_with_evidence,

        "evidence_conditioned_answer_accuracy":
            evidence_conditioned_accuracy,

        "mean_required_claim_recall":
            mean_non_null([
                condition[
                    "required_claim_recall"
                ]
                for condition in conditions
            ]),

        "mean_supporting_claim_recall":
            mean_non_null([
                condition[
                    "supporting_claim_recall"
                ]
                for condition in conditions
            ]),

        "mean_temporal_relation_accuracy":
            mean_non_null([
                condition[
                    "temporal_relation_accuracy"
                ]
                for condition in conditions
            ]),

        "unsupported_claim_count":
            unsupported_count,
    }


def calculate_a_to_b_sufficiency(
    scored_queries
):
    """
    Among queries correctly answered under human-selected
    evidence, determine how many remain correct under
    Experiment-A-selected evidence.
    """

    gt_answerable = [
        query
        for query in scored_queries
        if query[
            "conditions"
        ][
            "ground_truth_evidence"
        ][
            "metrics"
        ][
            "answer_correct"
        ]
    ]

    denominator = len(
        gt_answerable
    )

    if denominator == 0:
        return {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        }

    preserved = sum(
        1
        for query in gt_answerable
        if query[
            "conditions"
        ][
            "model_selected_evidence"
        ][
            "metrics"
        ][
            "answer_correct"
        ]
    )

    return {
        "numerator":
            preserved,

        "denominator":
            denominator,

        "rate":
            preserved / denominator,
    }


# ======================================================================
# Display
# ======================================================================

def format_metric(value):
    if value is None:
        return "N/A"

    return f"{value:.3f}"


def print_query_result(
    query_id,
    gt_metrics,
    a_metrics
):
    print("\n")
    print("=" * 60)
    print(query_id)
    print("=" * 60)

    print(
        f"{'Metric':30}"
        f"{'B-GT':>12}"
        f"{'B-A':>12}"
    )

    print("-" * 54)

    print(
        f"{'Answer correct':30}"
        f"{str(gt_metrics['answer_correct']):>12}"
        f"{str(a_metrics['answer_correct']):>12}"
    )

    print(
        f"{'Evidence available':30}"
        f"{str(gt_metrics['evidence_available']):>12}"
        f"{str(a_metrics['evidence_available']):>12}"
    )

    print(
        f"{'Required claim recall':30}"
        f"{format_metric(gt_metrics['required_claim_recall']):>12}"
        f"{format_metric(a_metrics['required_claim_recall']):>12}"
    )

    print(
        f"{'Supporting claim recall':30}"
        f"{format_metric(gt_metrics['supporting_claim_recall']):>12}"
        f"{format_metric(a_metrics['supporting_claim_recall']):>12}"
    )

    print(
        f"{'Temporal relation accuracy':30}"
        f"{format_metric(gt_metrics['temporal_relation_accuracy']):>12}"
        f"{format_metric(a_metrics['temporal_relation_accuracy']):>12}"
    )

    print(
        f"{'Unsupported claims':30}"
        f"{gt_metrics['unsupported_claim_count']:>12}"
        f"{a_metrics['unsupported_claim_count']:>12}"
    )


def print_summary(
    experiment_b,
    summary
):
    gt = summary[
        "ground_truth_evidence"
    ]

    a = summary[
        "model_selected_evidence"
    ]

    sufficiency = summary[
        "a_to_b_sufficiency"
    ]

    print("\n")
    print("=" * 72)
    print("Experiment B Scoring Summary")
    print("=" * 72)

    print(
        f"Model:  "
        f"{experiment_b.get('model_display_name')}"
    )

    print(
        f"Video:  "
        f"{experiment_b.get('video_id')}"
    )

    print()

    print(
        f"{'Metric':38}"
        f"{'B-GT':>14}"
        f"{'B-A':>14}"
    )

    print("-" * 66)

    print(
        f"{'Answer accuracy':38}"
        f"{format_metric(gt['answer_accuracy']):>14}"
        f"{format_metric(a['answer_accuracy']):>14}"
    )

    print(
        f"{'Evidence availability':38}"
        f"{format_metric(gt['evidence_availability_rate']):>14}"
        f"{format_metric(a['evidence_availability_rate']):>14}"
    )

    print(
        f"{'Evidence-conditioned answer accuracy':38}"
        f"{format_metric(gt['evidence_conditioned_answer_accuracy']):>14}"
        f"{format_metric(a['evidence_conditioned_answer_accuracy']):>14}"
    )

    print(
        f"{'Mean required-claim recall':38}"
        f"{format_metric(gt['mean_required_claim_recall']):>14}"
        f"{format_metric(a['mean_required_claim_recall']):>14}"
    )

    print(
        f"{'Mean supporting-claim recall':38}"
        f"{format_metric(gt['mean_supporting_claim_recall']):>14}"
        f"{format_metric(a['mean_supporting_claim_recall']):>14}"
    )

    print(
        f"{'Mean temporal-relation accuracy':38}"
        f"{format_metric(gt['mean_temporal_relation_accuracy']):>14}"
        f"{format_metric(a['mean_temporal_relation_accuracy']):>14}"
    )

    print(
        f"{'Unsupported claim count':38}"
        f"{gt['unsupported_claim_count']:>14}"
        f"{a['unsupported_claim_count']:>14}"
    )

    print()

    rate = sufficiency[
        "rate"
    ]

    if rate is None:
        print(
            "A->B sufficiency: N/A"
        )
    else:
        print(
            "A->B sufficiency: "
            f"{rate:.3f} "
            f"("
            f"{sufficiency['numerator']}/"
            f"{sufficiency['denominator']}"
            f")"
        )


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Score Experiment B using human "
            "answer/claim judgments."
        )
    )

    parser.add_argument(
        "--annotation",
        required=True,
        help="Ground-truth annotation JSON"
    )

    parser.add_argument(
        "--human-scores",
        required=True,
        help="Human scoring JSON"
    )

    parser.add_argument(
        "--experiment-b",
        required=True,
        help="Experiment B result JSON"
    )

    parser.add_argument(
        "--output-dir",
        default="results/experiment_b/scored",
        help="Directory for scored results"
    )

    args = parser.parse_args()

    # --------------------------------------------------------------
    # Load
    # --------------------------------------------------------------

    annotation = load_json(
        args.annotation
    )

    human_scores = load_json(
        args.human_scores
    )

    experiment_b = load_json(
        args.experiment_b
    )

    # --------------------------------------------------------------
    # Validate
    # --------------------------------------------------------------

    validate_all(
        annotation,
        human_scores,
        experiment_b
    )

    print(
        "Validation successful."
    )

    # --------------------------------------------------------------
    # Build lookups
    # --------------------------------------------------------------

    human_lookup = {
        q["query_id"]: q
        for q in human_scores[
            "queries"
        ]
    }

    # --------------------------------------------------------------
    # Score
    # --------------------------------------------------------------

    scored_queries = []

    for experiment_query in experiment_b[
        "queries"
    ]:
        query_id = experiment_query[
            "query_id"
        ]

        human_query = human_lookup[
            query_id
        ]

        scored_query = {
            "query_id":
                query_id,

            "query":
                experiment_query.get(
                    "query"
                ),

            "query_type":
                experiment_query.get(
                    "query_type"
                ),

            "ground_truth":
                experiment_query.get(
                    "ground_truth"
                ),

            "conditions": {},
        }

        for condition_name in [
            "ground_truth_evidence",
            "model_selected_evidence"
        ]:
            experiment_condition = (
                experiment_query[
                    "conditions"
                ][
                    condition_name
                ]
            )

            human_condition = (
                human_query[
                    condition_name
                ]
            )

            metrics = score_condition(
                human_condition,
                experiment_condition
            )

            scored_query[
                "conditions"
            ][
                condition_name
            ] = {
                "evidence_source":
                    experiment_condition.get(
                        "evidence_source"
                    ),

                "evidence_intervals":
                    experiment_condition.get(
                        "evidence_intervals",
                        []
                    ),

                "condition_status":
                    experiment_condition.get(
                        "condition_status"
                    ),

                "parsed_response":
                    experiment_condition.get(
                        "parsed_response"
                    ),

                "human_judgment":
                    human_condition,

                "metrics":
                    metrics,
            }

        print_query_result(
            query_id,
            scored_query[
                "conditions"
            ][
                "ground_truth_evidence"
            ][
                "metrics"
            ],
            scored_query[
                "conditions"
            ][
                "model_selected_evidence"
            ][
                "metrics"
            ]
        )

        scored_queries.append(
            scored_query
        )

    # --------------------------------------------------------------
    # Aggregate
    # --------------------------------------------------------------

    summary = {
        "ground_truth_evidence":
            aggregate_condition(
                scored_queries,
                "ground_truth_evidence"
            ),

        "model_selected_evidence":
            aggregate_condition(
                scored_queries,
                "model_selected_evidence"
            ),

        "a_to_b_sufficiency":
            calculate_a_to_b_sufficiency(
                scored_queries
            ),
    }

    # --------------------------------------------------------------
    # Complete output object
    # --------------------------------------------------------------

    scored_results = {
        "experiment":
            "B",

        "scoring":
            "human",

        "model":
            experiment_b.get(
                "model"
            ),

        "model_display_name":
            experiment_b.get(
                "model_display_name"
            ),

        "video_id":
            experiment_b.get(
                "video_id"
            ),

        "video_file":
            experiment_b.get(
                "video_file"
            ),

        "sources": {
            "annotation":
                os.path.abspath(
                    args.annotation
                ),

            "human_scores":
                os.path.abspath(
                    args.human_scores
                ),

            "experiment_b":
                os.path.abspath(
                    args.experiment_b
                ),
        },

        "queries":
            scored_queries,

        "summary":
            summary,
    }

    # --------------------------------------------------------------
    # Display summary
    # --------------------------------------------------------------

    print_summary(
        experiment_b,
        summary
    )

    # --------------------------------------------------------------
    # Save
    # --------------------------------------------------------------

    os.makedirs(
        args.output_dir,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_name = (
        f"{experiment_b['video_id']}_"
        f"{experiment_b['model']}_"
        f"scored_{timestamp}.json"
    )

    output_path = os.path.join(
        args.output_dir,
        output_name
    )

    save_json(
        output_path,
        scored_results
    )

    print(
        f"\nScored results saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()