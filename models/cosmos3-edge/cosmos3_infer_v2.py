#!/usr/bin/env python3

import argparse
import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor


def parse_args():
    parser = argparse.ArgumentParser(
        description="Answer a question about a video using a local Cosmos3-Edge model."
    )

    parser.add_argument(
        "--video-path",
        required=True,
        help="Path to the input video file.",
    )

    parser.add_argument(
        "--question",
        required=True,
        help="Question to ask about the video.",
    )

    parser.add_argument(
        "--fps",
        type=float,
        default=4.0,
        help="Number of video frames sampled per second. Default: 4.0",
    )

    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        help="Maximum number of generated answer tokens. Default: 256",
    )

    return parser.parse_args()


def validate_paths(model_path: Path, video_path: Path):
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model directory does not exist: {model_path}"
        )

    if not model_path.is_dir():
        raise NotADirectoryError(
            f"Model path is not a directory: {model_path}"
        )

    if not (model_path / "config.json").exists():
        raise FileNotFoundError(
            f"No config.json was found in the model directory: {model_path}"
        )

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video file does not exist: {video_path}"
        )

    if not video_path.is_file():
        raise FileNotFoundError(
            f"Video path is not a file: {video_path}"
        )


def select_dtype():
    if not torch.cuda.is_available():
        return torch.float32

    if torch.cuda.is_bf16_supported():
        return torch.bfloat16

    return torch.float16


def load_model(model_path: Path):
    dtype = select_dtype()

    print(f"Loading processor from: {model_path}")
    processor = AutoProcessor.from_pretrained(
        str(model_path),
        local_files_only=True,
    )

    print(f"Loading model with dtype: {dtype}")

    model_kwargs = {
        "local_files_only": True,
        "torch_dtype": dtype,
    }

    if torch.cuda.is_available():
        model_kwargs["device_map"] = "auto"

    model = AutoModelForImageTextToText.from_pretrained(
        str(model_path),
        **model_kwargs,
    )

    if not torch.cuda.is_available():
        model = model.to("cpu")

    model.eval()

    return processor, model


def get_input_device(model):
    try:
        return model.get_input_embeddings().weight.device
    except Exception:
        return next(model.parameters()).device


def move_inputs_to_device(inputs, device):
    moved_inputs = {}

    for name, value in inputs.items():
        if isinstance(value, torch.Tensor):
            moved_inputs[name] = value.to(device)
        else:
            moved_inputs[name] = value

    return moved_inputs


def answer_video_question(
    processor,
    model,
    video_path: Path,
    question: str,
    fps: float,
    max_new_tokens: int,
):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": str(video_path),
                    "fps": fps,
                },
                {
                    "type": "text",
                    "text": (
                        "Analyze the video in chronological order. "
                        "Use evidence from the entire video and pay attention "
                        "to actions, objects, people, and changes over time.\n\n"
                        f"Question: {question}"
                    ),
                },
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )

    input_device = get_input_device(model)
    inputs = move_inputs_to_device(inputs, input_device)

    prompt_length = inputs["input_ids"].shape[1]

    with torch.inference_mode():
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

    generated_answer_ids = generated_ids[:, prompt_length:]

    answer = processor.batch_decode(
        generated_answer_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )[0]

    return answer.strip()


def main():
    args = parse_args()

    model_path = Path("/opt/models/cosmos3-edge")
    video_path = Path(args.video_path).expanduser().resolve()

    try:
        validate_paths(model_path, video_path)

        processor, model = load_model(model_path)

        print(f"Processing video: {video_path}")
        print(f"Video sampling rate: {args.fps} FPS")
        print(f"Question: {args.question}")

        answer = answer_video_question(
            processor=processor,
            model=model,
            video_path=video_path,
            question=args.question,
            fps=args.fps,
            max_new_tokens=args.max_new_tokens,
        )

        print("\nAnswer:")
        print(answer)

    except Exception as error:
        print(
            f"\nError: {type(error).__name__}: {error}",
            file=sys.stderr,
        )

        if "cosmos3_edge" in str(error).lower():
            print(
                "\nYour Transformers installation may not include "
                "Cosmos3-Edge support. Install the current source version:\n\n"
                "pip uninstall -y transformers\n"
                "pip install --no-cache-dir "
                "git+https://github.com/huggingface/transformers.git",
                file=sys.stderr,
            )

        raise


if __name__ == "__main__":
    main()
