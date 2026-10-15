#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ANNOTATION_DIR="$PROJECT_ROOT/videos/counterfactual_vids/annotations"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/experiment_a_internvideo2_5.log"
FAIL_FILE="$LOG_DIR/experiment_a_internvideo2_5_failures.txt"

: > "$FAIL_FILE"

shopt -s nullglob
annotations=("$ANNOTATION_DIR"/*.json)

echo "Found ${#annotations[@]} annotations in $ANNOTATION_DIR"

if (( ${#annotations[@]} == 0 )); then
    echo "ERROR: No annotations found."
    exit 1
fi

for annotation in "${annotations[@]}"; do
    id="$(basename "$annotation" .json)"

    echo "========== Processing $id =========="

    if python3 "$SCRIPT_DIR/experiment_a.py" \
        --annotation "$annotation" \
        --model internvideo2_5 \
        --sample-fps 5 \
        >> "$LOG_FILE" 2>&1; then

        echo "COMPLETED: $id"
    else
        echo "$id" >> "$FAIL_FILE"
        echo "FAILED: $id"
    fi
done
echo "Batch complete."
echo "Log: $LOG_FILE"
echo "Failures: $FAIL_FILE"
