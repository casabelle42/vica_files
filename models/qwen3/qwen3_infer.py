#!/usr/bin/env python3

import argparse

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_PATH = "/opt/models/qwen3-14b"


def load_model(model_path):
    print(f"Loading tokenizer from {model_path}...")

    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True
    )
    
    model = AutoModelForCausalLM.from_pretrained(
      model_path,
      dtype=torch.bfloat16,
      device_map={"": "cuda:0"},
      local_files_only=True
    )

    model.eval()

    print("Model loaded.")
    print(f"Model device: {model.device}")
      
    return tokenizer, model


def generate_response(
    tokenizer,
    model,
    prompt,
    max_new_tokens=512
):
    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False
    )

    model_inputs = tokenizer(
        [text],
        return_tensors="pt"
    )

    # Put the input tensors on the same device as the model's
    # input embeddings.
    model_inputs = {
        key: value.to("cuda")
        for key, value in model_inputs.items()
    }
    
    input_length = model_inputs[
        "input_ids"
    ].shape[1]

    with torch.inference_mode():

        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False
        )

    # Remove the original prompt tokens.
    output_ids = generated_ids[
        0,
        input_length:
    ]

    response = tokenizer.decode(
        output_ids,
        skip_special_tokens=True
    )

    return response.strip()


def main():

    parser = argparse.ArgumentParser(
        description="Run Qwen3 text inference."
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="Prompt to send to Qwen3."
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="Read the prompt from a text file."
    )

    parser.add_argument(
        "--model-path",
        default=MODEL_PATH,
        help="Local Qwen3 model directory."
    )

    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=512,
        help="Maximum number of generated tokens."
    )

    args = parser.parse_args()

    if args.prompt_file:
    
        with open(
            args.prompt_file,
            "r",
            encoding="utf-8"
        ) as f:
            prompt = f.read().strip()
    
    elif args.prompt:
    
        prompt = args.prompt
    
    else:
    
        parser.error(
            "Either --prompt or --prompt-file is required."
        )
    
    tokenizer, model = load_model(
        args.model_path
    )

    response = generate_response(
        tokenizer,
        model,
        prompt,
        args.max_new_tokens
    )

    print()
    print("=== Qwen3 Response ===")
    print(response)
    print("=== End Response ===")


if __name__ == "__main__":
    main()