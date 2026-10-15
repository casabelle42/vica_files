#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys


PROJECT_ROOT = "/media/las_edge_account/Database/LAS-VICA"

CONTAINER_PROJECT_ROOT = "/workspace"

DEFAULT_SCORER_PROMPT = os.path.join(
    PROJECT_ROOT,
    "prompts",
    "BandCprompt_scorer.txt"
)

QWEN_CONTAINER = "qwen-scorer"

QWEN_SCRIPT = (
    "/workspace/models/qwen3/qwen3_infer.py"
)


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
# Annotation utilities
# ======================================================================

def build_entity_lookup(annotation):
    """
    Build a lookup from annotation entity IDs to their
    semantic descriptions.

    Example:
        P1 -> "man in dark polo shirt and khaki pants"
        O4 -> "door"
    """

    lookup = {}

    for entity in annotation.get(
        "entities",
        []
    ):

        entity_id = entity.get(
            "entity_id"
        )

        description = entity.get(
            "description"
        )

        if (
            isinstance(entity_id, str)
            and isinstance(description, str)
            and description.strip()
        ):

            lookup[entity_id] = (
                description.strip()
            )

    return lookup


def resolve_required_claims(
    annotation,
    required_claims
):
    """
    Convert annotation references into semantic components
    that can be evaluated by Qwen.

    Example annotation claim:

        {
            "claim_id": "Q5_C1",
            "entity_id": "P1",
            "action": "walk toward",
            "object_id": "O4",
            "event_ids": ["E6"]
        }

    becomes:

        {
            "claim_id": "Q5_C1",
            "components": {
                "entity":
                    "man in dark polo shirt and khaki pants",
                "action":
                    "walk toward",
                "object":
                    "door"
            }
        }

    event_ids are annotation metadata and are not scored as
    semantic answer components.
    """

    entity_lookup = build_entity_lookup(
        annotation
    )

    resolved = []

    for claim in required_claims:

        claim_id = claim.get(
            "claim_id"
        )

        if not isinstance(
            claim_id,
            str
        ):

            raise ValueError(
                "Required claim is missing "
                "a valid claim_id."
            )

        components = {}

        # ----------------------------------------------------------
        # Entity
        # ----------------------------------------------------------

        entity_id = claim.get(
            "entity_id"
        )

        if entity_id is not None:

            if entity_id not in entity_lookup:

                raise ValueError(
                    f"{claim_id}: unknown "
                    f"entity_id {entity_id}"
                )

            components[
                "entity"
            ] = entity_lookup[
                entity_id
            ]

        # ----------------------------------------------------------
        # Action
        # ----------------------------------------------------------

        action = claim.get(
            "action"
        )

        if (
            isinstance(action, str)
            and action.strip()
        ):

            components[
                "action"
            ] = action.strip()

        # ----------------------------------------------------------
        # Object
        # ----------------------------------------------------------

        object_id = claim.get(
            "object_id"
        )

        if object_id is not None:

            if object_id not in entity_lookup:

                raise ValueError(
                    f"{claim_id}: unknown "
                    f"object_id {object_id}"
                )

            components[
                "object"
            ] = entity_lookup[
                object_id
            ]

        # ----------------------------------------------------------
        # Other explicit semantic fields
        # ----------------------------------------------------------

        for field in (
            "location",
            "state",
            "attribute",
        ):

            value = claim.get(
                field
            )

            if (
                isinstance(value, str)
                and value.strip()
            ):

                components[
                    field
                ] = value.strip()

        if not components:

            raise ValueError(
                f"{claim_id}: no semantic "
                "components could be resolved."
            )

        resolved.append({
            "claim_id":
                claim_id,

            "components":
                components,
        })

    return resolved


def find_query(
    annotation,
    query_id
):

    for query in annotation.get(
        "queries",
        []
    ):

        if query.get(
            "query_id"
        ) == query_id:

            return query

    raise ValueError(
        f"Query not found: {query_id}"
    )


def get_reference_data(
    annotation,
    query
):
    """
    Extract and resolve the annotation information needed
    by the Qwen scorer.

    Required claims are converted from annotation IDs into
    semantic components.

    Supporting claims provide reference context but do not
    count toward required-claim recall.

    Temporal relations are evaluated separately.
    """

    ground_truth = query[
        "ground_truth"
    ]

    required_claims = (
        ground_truth.get(
            "required_claims",
            []
        )
    )

    resolved_required_claims = (
        resolve_required_claims(
            annotation,
            required_claims
        )
    )

    return {
        "query":
            query["query"],
        "answer_type":
            query.get("answer_type"),
        "reference_answer":
            ground_truth.get(
                "answer",
                ""
            ),

        "required_claims":
            resolved_required_claims,

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
    }


# ======================================================================
# Scorer prompt
# ======================================================================

def build_scorer_prompt(
    frozen_prompt,
    reference_data,
    candidate_answer
):

    scorer_input = {
        "query":
            reference_data[
                "query"
            ],
        "answer_type": 
            reference_data[
                "answer_type"
            ],
        "reference_answer":
            reference_data[
                "reference_answer"
            ],

        "required_claims":
            reference_data[
                "required_claims"
            ],

        "supporting_claims":
            reference_data[
                "supporting_claims"
            ],

        "temporal_relations":
            reference_data[
                "temporal_relations"
            ],

        "candidate_answer":
            candidate_answer,
    }

    output_schema = {
        "required_claims": [
            {
                "claim_id":
                    "<claim_id>",

                "components": {
                    "<component_name>":
                        (
                            "SUPPORTED | "
                            "CONTRADICTED | "
                            "NOT_MENTIONED"
                        )
                }
            }
        ],

        "temporal_relations": [
            {
                "relation_id":
                    "<relation_id>",

                "classification":
                    (
                        "SUPPORTED | "
                        "CONTRADICTED | "
                        "NOT_MENTIONED"
                    )
            }
        ],

        "candidate_claims": [
            {
                "text":
                    "<substantive factual claim>",

                "classification":
                    "SUPPORTED | UNSUPPORTED"
            }
        ]
    }

    return (
        frozen_prompt.rstrip()
        + "\n\n"
        + "SCORER INPUT\n\n"
        + json.dumps(
            scorer_input,
            indent=2,
            ensure_ascii=False
        )
        + "\n\n"
        + "REQUIRED OUTPUT SCHEMA\n\n"
        + json.dumps(
            output_schema,
            indent=2,
            ensure_ascii=False
        )
        + "\n\n"
        + (
            "Return one JSON object matching "
            "the required output schema."
        )
    )


# ======================================================================
# Qwen execution
# ======================================================================

def run_qwen(prompt):

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

        QWEN_CONTAINER,

        QWEN_SCRIPT,

        "--prompt",
        prompt,

        "--max-new-tokens",
        "2048",
    ]

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
# Extract Qwen response
# ======================================================================

def extract_qwen_response(stdout):

    pattern = re.compile(
        r"=== Qwen3 Response ==="
        r"\s*(.*?)\s*"
        r"=== End Response ===",
        flags=re.DOTALL
    )

    match = pattern.search(
        stdout
    )

    if match:

        return match.group(1).strip()

    return stdout.strip()


def strip_json_fence(text):

    text = text.strip()

    match = re.fullmatch(
        r"```(?:json)?\s*"
        r"(.*?)"
        r"\s*```",
        text,
        flags=(
            re.DOTALL
            | re.IGNORECASE
        )
    )

    if match:

        return match.group(1).strip()

    return text


# ======================================================================
# Scorer response validation
# ======================================================================

REQUIRED_CLASSIFICATIONS = {
    "SUPPORTED",
    "CONTRADICTED",
    "NOT_MENTIONED",
}

CANDIDATE_CLASSIFICATIONS = {
    "SUPPORTED",
    "UNSUPPORTED",
}


def validate_scorer_response(
    parsed,
    reference_data
):

    errors = []

    if not isinstance(
        parsed,
        dict
    ):

        return [
            "Top-level scorer response "
            "must be an object."
        ]

    # --------------------------------------------------------------
    # Required claims
    # --------------------------------------------------------------

    required_results = parsed.get(
        "required_claims"
    )

    if not isinstance(
        required_results,
        list
    ):

        errors.append(
            "required_claims must be a list."
        )

        required_results = []

    expected_claims = {
        claim.get("claim_id"):
            claim

        for claim in reference_data[
            "required_claims"
        ]
    }

    returned_claims = {}

    for item in required_results:

        if not isinstance(
            item,
            dict
        ):

            errors.append(
                "required_claims contains "
                "a non-object item."
            )

            continue

        claim_id = item.get(
            "claim_id"
        )

        if claim_id not in expected_claims:

            errors.append(
                "Unexpected claim_id: "
                f"{claim_id}"
            )

            continue

        if claim_id in returned_claims:

            errors.append(
                "Duplicate claim_id: "
                f"{claim_id}"
            )

            continue

        returned_claims[
            claim_id
        ] = item

        components = item.get(
            "components"
        )

        if not isinstance(
            components,
            dict
        ):

            errors.append(
                f"{claim_id}: components "
                "must be an object."
            )

            continue

        # ----------------------------------------------------------
        # IMPORTANT:
        #
        # Expected semantic components now come from the resolved
        # "components" object, not directly from annotation keys.
        #
        # Therefore:
        #
        #   entity_id -> entity
        #   object_id -> object
        #   event_ids -> not scored as a component
        # ----------------------------------------------------------

        expected_components = set(
            expected_claims[
                claim_id
            ][
                "components"
            ].keys()
        )

        returned_components = set(
            components.keys()
        )

        missing_components = (
            expected_components
            - returned_components
        )

        extra_components = (
            returned_components
            - expected_components
        )

        for component in sorted(
            missing_components
        ):

            errors.append(
                f"{claim_id}: missing "
                f"component {component}"
            )

        for component in sorted(
            extra_components
        ):

            errors.append(
                f"{claim_id}: unexpected "
                f"component {component}"
            )

        for (
            component,
            classification
        ) in components.items():

            if classification not in (
                REQUIRED_CLASSIFICATIONS
            ):

                errors.append(
                    f"{claim_id}.{component}: "
                    "invalid classification "
                    f"{classification}"
                )

    for claim_id in expected_claims:

        if claim_id not in returned_claims:

            errors.append(
                "Missing required claim: "
                f"{claim_id}"
            )

    # --------------------------------------------------------------
    # Temporal relations
    # --------------------------------------------------------------

    relation_results = parsed.get(
        "temporal_relations"
    )

    if not isinstance(
        relation_results,
        list
    ):

        errors.append(
            "temporal_relations "
            "must be a list."
        )

        relation_results = []

    expected_relations = {
        relation.get(
            "relation_id"
        ):
            relation

        for relation in reference_data[
            "temporal_relations"
        ]
    }

    returned_relations = {}

    for item in relation_results:

        if not isinstance(
            item,
            dict
        ):

            errors.append(
                "temporal_relations contains "
                "a non-object item."
            )

            continue

        relation_id = item.get(
            "relation_id"
        )

        if relation_id not in (
            expected_relations
        ):

            errors.append(
                "Unexpected relation_id: "
                f"{relation_id}"
            )

            continue

        if relation_id in (
            returned_relations
        ):

            errors.append(
                "Duplicate relation_id: "
                f"{relation_id}"
            )

            continue

        returned_relations[
            relation_id
        ] = item

        classification = item.get(
            "classification"
        )

        if classification not in (
            REQUIRED_CLASSIFICATIONS
        ):

            errors.append(
                f"{relation_id}: invalid "
                "classification "
                f"{classification}"
            )

    for relation_id in expected_relations:

        if relation_id not in (
            returned_relations
        ):

            errors.append(
                "Missing temporal relation: "
                f"{relation_id}"
            )

    # --------------------------------------------------------------
    # Candidate claims
    # --------------------------------------------------------------

    candidate_claims = parsed.get(
        "candidate_claims"
    )

    if not isinstance(
        candidate_claims,
        list
    ):

        errors.append(
            "candidate_claims "
            "must be a list."
        )

        candidate_claims = []

    for index, item in enumerate(
        candidate_claims
    ):

        if not isinstance(
            item,
            dict
        ):

            errors.append(
                "candidate_claims item "
                f"{index} is not an object."
            )

            continue

        text = item.get(
            "text"
        )

        classification = item.get(
            "classification"
        )

        if (
            not isinstance(text, str)
            or not text.strip()
        ):

            errors.append(
                "candidate_claims item "
                f"{index} has invalid text."
            )

        if classification not in (
            CANDIDATE_CLASSIFICATIONS
        ):

            errors.append(
                "candidate_claims item "
                f"{index} has invalid "
                f"classification "
                f"{classification}"
            )

    return errors


def parse_scorer_response(
    response_text,
    reference_data
):

    cleaned = strip_json_fence(
        response_text
    )

    try:

        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError as exc:

        return {
            "parse_success":
                False,

            "validation_success":
                False,

            "validation_errors": [
                f"Invalid JSON: {exc}"
            ],

            "parsed":
                None,
        }

    errors = validate_scorer_response(
        parsed,
        reference_data
    )

    return {
        "parse_success":
            True,

        "validation_success":
            len(errors) == 0,

        "validation_errors":
            errors,

        "parsed":
            parsed,
    }


# ======================================================================
# Metric calculation
# ======================================================================

def safe_ratio(
    numerator,
    denominator
):

    if denominator == 0:
        return None

    return numerator / denominator


def calculate_metrics(
    scorer_output,
    reference_data
):

    # --------------------------------------------------------------
    # Required components
    # --------------------------------------------------------------

    component_totals = {}
    component_supported = {}
    component_contradicted = {}
    component_not_mentioned = {}

    total_components = 0
    supported_components = 0
    contradicted_components = 0
    not_mentioned_components = 0

    complete_claims = 0

    required_results = {
        item["claim_id"]:
            item

        for item in scorer_output[
            "required_claims"
        ]
    }

    for reference_claim in (
        reference_data[
            "required_claims"
        ]
    ):

        claim_id = reference_claim[
            "claim_id"
        ]

        result = required_results[
            claim_id
        ]

        components = result[
            "components"
        ]

        # The annotation-derived semantic components determine
        # exactly which components contribute to the metrics.

        expected_components = (
            reference_claim[
                "components"
            ]
        )

        claim_fully_supported = True

        for component_name in (
            expected_components
        ):

            classification = components[
                component_name
            ]

            total_components += 1

            component_totals[
                component_name
            ] = (
                component_totals.get(
                    component_name,
                    0
                )
                + 1
            )

            if (
                classification
                == "SUPPORTED"
            ):

                supported_components += 1

                component_supported[
                    component_name
                ] = (
                    component_supported.get(
                        component_name,
                        0
                    )
                    + 1
                )

            elif (
                classification
                == "CONTRADICTED"
            ):

                contradicted_components += 1

                component_contradicted[
                    component_name
                ] = (
                    component_contradicted.get(
                        component_name,
                        0
                    )
                    + 1
                )

                claim_fully_supported = False

            elif (
                classification
                == "NOT_MENTIONED"
            ):

                not_mentioned_components += 1

                component_not_mentioned[
                    component_name
                ] = (
                    component_not_mentioned.get(
                        component_name,
                        0
                    )
                    + 1
                )

                claim_fully_supported = False

        if claim_fully_supported:

            complete_claims += 1

    total_required_claims = len(
        reference_data[
            "required_claims"
        ]
    )

    # --------------------------------------------------------------
    # Component-specific accuracy
    # --------------------------------------------------------------

    component_accuracy = {}

    for component_name in (
        component_totals
    ):

        component_accuracy[
            component_name
        ] = safe_ratio(
            component_supported.get(
                component_name,
                0
            ),
            component_totals[
                component_name
            ]
        )

    # --------------------------------------------------------------
    # Temporal relations
    # --------------------------------------------------------------

    temporal_results = scorer_output[
        "temporal_relations"
    ]

    temporal_total = len(
        temporal_results
    )

    temporal_supported = sum(
        1
        for item in temporal_results
        if item[
            "classification"
        ] == "SUPPORTED"
    )

    temporal_contradicted = sum(
        1
        for item in temporal_results
        if item[
            "classification"
        ] == "CONTRADICTED"
    )

    temporal_not_mentioned = sum(
        1
        for item in temporal_results
        if item[
            "classification"
        ] == "NOT_MENTIONED"
    )

    # --------------------------------------------------------------
    # Candidate claims / precision
    # --------------------------------------------------------------

    candidate_claims = scorer_output[
        "candidate_claims"
    ]

    candidate_total = len(
        candidate_claims
    )

    candidate_supported = sum(
        1
        for item in candidate_claims
        if item[
            "classification"
        ] == "SUPPORTED"
    )

    candidate_unsupported = sum(
        1
        for item in candidate_claims
        if item[
            "classification"
        ] == "UNSUPPORTED"
    )

    # --------------------------------------------------------------
    # Final metrics
    # --------------------------------------------------------------

    return {
        "atomic_component_recall":
            safe_ratio(
                supported_components,
                total_components
            ),

        "required_claim_recall":
            safe_ratio(
                complete_claims,
                total_required_claims
            ),

        "atomic_claim_precision":
            safe_ratio(
                candidate_supported,
                candidate_total
            ),

        "unsupported_claim_rate":
            safe_ratio(
                candidate_unsupported,
                candidate_total
            ),

        "temporal_relation_accuracy":
            safe_ratio(
                temporal_supported,
                temporal_total
            ),

        "component_accuracy":
            component_accuracy,

        "counts": {
            "required_components_total":
                total_components,

            "required_components_supported":
                supported_components,

            "required_components_contradicted":
                contradicted_components,

            "required_components_not_mentioned":
                not_mentioned_components,

            "required_claims_total":
                total_required_claims,

            "required_claims_fully_supported":
                complete_claims,

            "candidate_claims_total":
                candidate_total,

            "candidate_claims_supported":
                candidate_supported,

            "candidate_claims_unsupported":
                candidate_unsupported,

            "temporal_relations_total":
                temporal_total,

            "temporal_relations_supported":
                temporal_supported,

            "temporal_relations_contradicted":
                temporal_contradicted,

            "temporal_relations_not_mentioned":
                temporal_not_mentioned,
        }
    }


# ======================================================================
# Console output
# ======================================================================

def print_metrics(metrics):

    print()
    print("=" * 60)
    print("Scoring Results")
    print("=" * 60)

    def show_metric(
        name,
        value
    ):

        if value is None:

            formatted = "N/A"

        else:

            formatted = (
                f"{value:.3f}"
            )

        print(
            f"{name:<30}"
            f"{formatted}"
        )

    show_metric(
        "Atomic component recall:",
        metrics[
            "atomic_component_recall"
        ]
    )

    show_metric(
        "Required claim recall:",
        metrics[
            "required_claim_recall"
        ]
    )

    show_metric(
        "Atomic claim precision:",
        metrics[
            "atomic_claim_precision"
        ]
    )

    show_metric(
        "Unsupported claim rate:",
        metrics[
            "unsupported_claim_rate"
        ]
    )

    show_metric(
        "Temporal relation accuracy:",
        metrics[
            "temporal_relation_accuracy"
        ]
    )

    print()
    print("Component accuracy:")

    for (
        component,
        accuracy
    ) in metrics[
        "component_accuracy"
    ].items():

        show_metric(
            f"  {component}:",
            accuracy
        )




class PersistentQwenScorer:
    """One Docker process and one Qwen model load per scoring batch."""
    def __init__(self, image=QWEN_CONTAINER, script=QWEN_SCRIPT,
                 project_root=PROJECT_ROOT, max_new_tokens=2048):
        self.image, self.script = image, script
        self.project_root = project_root
        self.max_new_tokens = max_new_tokens
        self.process = None

    def __enter__(self):
        command = ["docker", "run", "--rm", "-i", "--runtime", "nvidia",
                   "--ipc=host", "--ulimit", "memlock=-1",
                   "--ulimit", "stack=67108864",
                   "-v", f"{self.project_root}:{CONTAINER_PROJECT_ROOT}",
                   "--entrypoint", "python3", self.image, self.script,
                   "--serve-stdio", "--max-new-tokens", str(self.max_new_tokens)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=None,
                                        text=True, bufsize=1)
        return self

    def score(self, prompt):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Qwen scoring process is not running")
        request = json.dumps({"prompt": prompt,
                              "max_new_tokens": self.max_new_tokens},
                             ensure_ascii=False)
        self.process.stdin.write(request + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Qwen process ended without a response")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "Qwen generation failed"))
        return reply["response"]

    def __exit__(self, exc_type, exc, tb):
        if self.process is not None:
            if self.process.poll() is None:
                try:
                    self.process.stdin.write('{"command":"shutdown"}\n')
                    self.process.stdin.flush()
                    self.process.stdin.close()
                    self.process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
            self.process.stdout.close()


def score_candidate(annotation, query_id, candidate_answer, frozen_prompt, session):
    """Shared B/C scorer; Qwen session is reused across calls."""
    query = find_query(annotation, query_id)
    reference_data = get_reference_data(annotation, query)
    prompt = build_scorer_prompt(frozen_prompt, reference_data, candidate_answer)
    response_text = session.score(prompt)
    parsed = parse_scorer_response(response_text, reference_data)
    result = {"query_id": query_id, "candidate_answer": candidate_answer,
              "raw_scorer_response": response_text,
              "parse_success": parsed["parse_success"],
              "validation_success": parsed["validation_success"],
              "validation_errors": parsed["validation_errors"],
              "judgments": parsed["parsed"], "metrics": None}
    if parsed["validation_success"]:
        result["metrics"] = calculate_metrics(parsed["parsed"], reference_data)
    return result


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Score one LAS-VICA B/C "
            "candidate answer using Qwen3."
        )
    )

    parser.add_argument(
        "--annotation",
        required=True,
        help="Annotation JSON file."
    )

    parser.add_argument(
        "--query-id",
        required=True,
        help="Query ID, for example Q3."
    )

    parser.add_argument(
        "--candidate-answer",
        required=True,
        help=(
            "Candidate VLM answer "
            "to evaluate."
        )
    )

    parser.add_argument(
        "--scorer-prompt",
        default=DEFAULT_SCORER_PROMPT,
        help=(
            "Frozen B/C scorer prompt."
        )
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional JSON output file."
        )
    )

    args = parser.parse_args()

    # --------------------------------------------------------------
    # Load annotation and prompt
    # --------------------------------------------------------------

    annotation = load_json(
        args.annotation
    )

    frozen_prompt = load_text(
        args.scorer_prompt
    )

    query = find_query(
        annotation,
        args.query_id
    )

    reference_data = get_reference_data(
        annotation,
        query
    )

    # --------------------------------------------------------------
    # Build scorer input
    # --------------------------------------------------------------

    scorer_prompt = build_scorer_prompt(
        frozen_prompt,
        reference_data,
        args.candidate_answer
    )

    print(
        f"Scoring "
        f"{annotation['video_id']} "
        f"{args.query_id}..."
    )

    # --------------------------------------------------------------
    # Run Qwen
    # --------------------------------------------------------------

    execution = run_qwen(
        scorer_prompt
    )

    if not execution[
        "execution_success"
    ]:

        print(
            "Qwen scorer execution failed.",
            file=sys.stderr
        )

        print(
            execution["stderr"],
            file=sys.stderr
        )

        sys.exit(1)

    response_text = (
        extract_qwen_response(
            execution["stdout"]
        )
    )

    # --------------------------------------------------------------
    # Parse / validate
    # --------------------------------------------------------------

    parsed = parse_scorer_response(
        response_text,
        reference_data
    )

    if not parsed[
        "parse_success"
    ]:

        print(
            "Scorer returned invalid JSON.",
            file=sys.stderr
        )

        print(
            response_text,
            file=sys.stderr
        )

        sys.exit(1)

    if not parsed[
        "validation_success"
    ]:

        print(
            "Scorer response failed "
            "validation:",
            file=sys.stderr
        )

        for error in parsed[
            "validation_errors"
        ]:

            print(
                f"  - {error}",
                file=sys.stderr
            )

        print()
        print("Raw scorer output:")

        print(
            json.dumps(
                parsed["parsed"],
                indent=2,
                ensure_ascii=False
            )
        )

        sys.exit(1)

    # --------------------------------------------------------------
    # Calculate deterministic metrics
    # --------------------------------------------------------------

    metrics = calculate_metrics(
        parsed["parsed"],
        reference_data
    )

    print()
    print("Qwen judgments:")

    print(
        json.dumps(
            parsed["parsed"],
            indent=2,
            ensure_ascii=False
        )
    )

    print_metrics(
        metrics
    )

    # --------------------------------------------------------------
    # Complete result record
    # --------------------------------------------------------------

    result = {
        "video_id":
            annotation[
                "video_id"
            ],

        "query_id":
            args.query_id,

        "query":
            reference_data[
                "query"
            ],

        "candidate_answer":
            args.candidate_answer,

        "scorer": {
            "model":
                "Qwen3-14B",

            "prompt_file":
                os.path.relpath(
                    args.scorer_prompt,
                    PROJECT_ROOT
                ),
        },

        "reference": {
            "answer":
                reference_data[
                    "reference_answer"
                ],

            "required_claims":
                reference_data[
                    "required_claims"
                ],

            "temporal_relations":
                reference_data[
                    "temporal_relations"
                ],
        },

        "judgments":
            parsed["parsed"],

        "metrics":
            metrics,
    }

    # --------------------------------------------------------------
    # Optional output
    # --------------------------------------------------------------

    if args.output:

        output_dir = os.path.dirname(
            os.path.abspath(
                args.output
            )
        )

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        with open(
            args.output,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                result,
                f,
                indent=2,
                ensure_ascii=False
            )

        print()
        print(
            "Scoring result saved to:"
        )

        print(
            args.output
        )


if __name__ == "__main__":
    main()
