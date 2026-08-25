#!/bin/bash
set -e

VIDEO_PATH="$1"
MAX_FRAMES="$2"
QUESTION="$3"

if [ -z "$VIDEO_PATH" ] || [ -z "$MAX_FRAMES" ] || [ -z "$QUESTION" ]; then
    echo "Usage: run_cosmos-reason2_query.sh <video_path> <max_frames> \"<question>\""
    exit 1
fi

python3 /workspace/models/cosmos-reason2/cosmos-reason2_infer.py "$VIDEO_PATH" "$MAX_FRAMES" "$QUESTION"
    
