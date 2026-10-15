mkdir -p logs
: > logs/experiment_a_cosmos3_failures.txt

for annotation in videos/counterfactual_vids/annotations/*.json; do
    id=$(basename "$annotation" .json)

    echo "========== Processing $id =========="

    if ! python3 evaluation/experiment_a.py \
        --annotation "$annotation" \
        --model cosmos3 \
        --sample-fps 5 \
        >> logs/experiment_a_cosmos3.log 2>&1; then

        echo "$id" >> logs/experiment_a_cosmos3_failures.txt
        echo "FAILED: $id"
    else
        echo "COMPLETED: $id"
    fi
done
