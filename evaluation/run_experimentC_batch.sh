#!/usr/bin/env bash
set -uo pipefail

PROJECT_ROOT="/media/las_edge_account/Database/LAS-VICA"
MODEL="${1:-cosmos_reason2}"
SAMPLE_FPS="${SAMPLE_FPS:-5}"
RETRY_FAILED="${RETRY_FAILED:-0}"
FORCE="${FORCE:-0}"

case "$MODEL" in
  cosmos_reason2|cosmos3|internvideo2_5) ;;
  *) echo "Usage: $0 [cosmos_reason2|cosmos3|internvideo2_5]" >&2; exit 2 ;;
esac

cd "$PROJECT_ROOT" || exit 1
ANNOTATION_DIR="videos/counterfactual_vids/annotations"
OUTPUT_DIR="results/experiment_c/${MODEL}"
LOG_DIR="results/experiment_c/logs"
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"
LOG_FILE="$LOG_DIR/${MODEL}_$(date +%Y%m%d_%H%M%S).log"

shopt -s nullglob
annotations=("$ANNOTATION_DIR"/*.json)
if (( ${#annotations[@]} == 0 )); then
  echo "No annotations found in $ANNOTATION_DIR" >&2
  exit 1
fi

printf 'Model: %s | Annotations: %d | FPS: %s\n' "$MODEL" "${#annotations[@]}" "$SAMPLE_FPS" | tee -a "$LOG_FILE"
failed=0
for annotation in "${annotations[@]}"; do
  video_id="$(basename "$annotation" .json)"
  output_file="$OUTPUT_DIR/${video_id}_${MODEL}.json"
  args=(
    --model "$MODEL"
    --annotation "$annotation"
    --sample-fps "$SAMPLE_FPS"
    --output-dir "$OUTPUT_DIR"
    --output-file "$output_file"
  )
  if [[ -f "$output_file" ]]; then
    args+=(--resume)
    if [[ "$RETRY_FAILED" == "1" ]]; then args+=(--retry-failed); fi
    if [[ "$FORCE" == "1" ]]; then args+=(--force); fi
  fi

  echo "[$(date '+%F %T')] START $video_id" | tee -a "$LOG_FILE"
  if python3 evaluation/experiment_c.py "${args[@]}" >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%F %T')] OK    $video_id" | tee -a "$LOG_FILE"
  else
    echo "[$(date '+%F %T')] FAIL  $video_id (see $LOG_FILE)" | tee -a "$LOG_FILE"
    ((failed+=1))
  fi
done
printf 'Completed batch; failed videos: %d; log: %s\n' "$failed" "$LOG_FILE" | tee -a "$LOG_FILE"
((failed == 0))
