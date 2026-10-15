for annotation in videos/counterfactual_vids/annotations/*.json; do
    video_id=$(basename "$annotation" .json)

    experiment_a=$(find results/experiment_a -maxdepth 1 -type f \
        -name "${video_id}_cosmos3_*.json" \
        | sort | tail -n 1)

    if [[ -z "$experiment_a" ]]; then
        echo "WARNING: No Experiment A result for $video_id"
        continue
    fi

    echo "========================================"
    echo "Running Experiment B: $video_id"
    echo "Experiment A source: $experiment_a"
    echo "========================================"

    python3 evaluation/experiment_b.py \
        --annotation "$annotation" \
        --experiment-a "$experiment_a" \
        --model cosmos3 \
        --sample-fps 5

    if [[ $? -ne 0 ]]; then
        echo "ERROR: Experiment B failed for $video_id"
    fi
done
