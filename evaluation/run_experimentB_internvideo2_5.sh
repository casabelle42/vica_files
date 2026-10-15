#!/usr/bin/env bash
set -uo pipefail

PROJECT_ROOT="/media/las_edge_account/Database/LAS-VICA"
MODEL="internvideo2_5"
SAMPLE_FPS="${SAMPLE_FPS:-5}"
FORCE="${FORCE:-0}"

cd "$PROJECT_ROOT" || exit 1
ANNOTATION_DIR="videos/counterfactual_vids/annotations"
A_DIR="results/experiment_a"
B_DIR="results/experiment_b"
LOG_DIR="$B_DIR/logs"
mkdir -p "$B_DIR" "$LOG_DIR"
LOG_FILE="$LOG_DIR/${MODEL}_$(date +%Y%m%d_%H%M%S).log"

shopt -s nullglob
annotations=("$ANNOTATION_DIR"/*.json)
if (( ${#annotations[@]} == 0 )); then
  echo "No annotations found in $ANNOTATION_DIR" >&2
  exit 1
fi

printf 'Experiment B | Model: %s | Annotations: %d | FPS: %s\n' \
  "$MODEL" "${#annotations[@]}" "$SAMPLE_FPS" | tee -a "$LOG_FILE"

ok=0; skipped=0; failed=0
for annotation in "${annotations[@]}"; do
  video_id="$(basename "$annotation" .json)"

  # Experiment A produces timestamped files, so select the newest matching source.
  a_files=("$A_DIR/${video_id}_${MODEL}_"*.json)
  if (( ${#a_files[@]} == 0 )); then
    echo "SKIP $video_id: no matching Experiment A result" | tee -a "$LOG_FILE"
    ((skipped+=1))
    continue
  fi
  a_file="$(printf '%s\n' "${a_files[@]}" | sort -r | head -n 1)"

  # Experiment B also writes timestamped files; avoid duplicate runs.
  b_files=("$B_DIR/${video_id}_${MODEL}_"*.json)
  if (( ${#b_files[@]} > 0 )) && [[ "$FORCE" != "1" ]]; then
    echo "SKIP $video_id: Experiment B result already exists (FORCE=1 to rerun)" | tee -a "$LOG_FILE"
    ((skipped+=1))
    continue
  fi

  echo "[$(date '+%F %T')] START $video_id | A source: $(basename "$a_file")" | tee -a "$LOG_FILE"
  if python3 evaluation/experiment_b.py \
      --annotation "$annotation" \
      --experiment-a "$a_file" \
      --model "$MODEL" \
      --sample-fps "$SAMPLE_FPS" \
      --results-dir "$B_DIR" >>"$LOG_FILE" 2>&1; then
    echo "[$(date '+%F %T')] OK $video_id" | tee -a "$LOG_FILE"
    ((ok+=1))
  else
    echo "[$(date '+%F %T')] FAIL $video_id (see $LOG_FILE)" | tee -a "$LOG_FILE"
    ((failed+=1))
  fi
done

echo "Complete | OK: $ok | Skipped: $skipped | Failed: $failed | Log: $LOG_FILE" | tee -a "$LOG_FILE"
(( failed == 0 ))
