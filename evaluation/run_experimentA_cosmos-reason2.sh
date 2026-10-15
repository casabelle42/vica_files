mkdir -p logs
: > logs/experiment_a_cosmos_reason2_failures.txt

for annotation in videos/counterfactual_vids/annotations/*.json; do
    id=$(basename "$annotation" .json)

    echo "========== Processing $id =========="

    if ! python3 evaluation/experiment_a.py \
        --annotation "$annotation" \
        --model cosmos_reason2 \
        --sample-fps 5 \
        >> logs/experiment_a_cosmos_reason2.log 2>&1; then

        echo "$id" >> logs/experiment_a_cosmos_reason2_failures.txt
        echo "FAILED: $id"
    else
        echo "COMPLETED: $id"
    fi
done
