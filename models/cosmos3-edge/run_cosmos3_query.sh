#!/bin/bash
set -e

VIDEO_PATH="$1"
MAX_FRAMES="$2"
QUESTION="$3"

if [ -z "$VIDEO_PATH" ] || [ -z "$MAX_FRAMES" ] || [ -z "$QUESTION" ]; then
    echo "Usage: run_cosmos3_query.sh <video_path> <max_frames> \"<question>\""
    exit 1
fi

python3 /workspace/models/cosmos3-edge/cosmos3_infer.py \
    --video "$VIDEO_PATH" \
    --num_frames "$MAX_FRAMES" \
    --prompt "$QUESTION"
    