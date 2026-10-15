#!/usr/bin/env python3

import argparse
import json
import os
from datetime import datetime

import cv2
import numpy as np
import torch

from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
)


# ======================================================================
# Configuration
# ======================================================================

DEFAULT_MODEL_PATH = "/opt/models/cosmos3-edge/"
IMAGE_SIZE = 448


# ======================================================================
# Video utilities
# ======================================================================

def get_video_info(video_path):
    """
    Return basic video metadata.
    """

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open video: {video_path}"
        )

    frame_count = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    source_fps = float(
        cap.get(cv2.CAP_PROP_FPS)
    )

    if frame_count <= 0:
        cap.release()
        raise RuntimeError(
            f"Video has no frames: {video_path}"
        )

    if source_fps <= 0:
        cap.release()
        raise RuntimeError(
            f"Invalid video FPS: {source_fps}"
        )

    duration = frame_count / source_fps

    cap.release()

    return {
        "frame_count": frame_count,
        "source_fps": source_fps,
        "duration": duration,
    }


def prepare_frame(frame):
    """
    Convert an OpenCV BGR frame to RGB uint8.

    Frames are resized to 448x448 to preserve the input format used by
    the previous Cosmos3 inference implementation.
    """

    frame_rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    frame_resized = cv2.resize(
        frame_rgb,
        (IMAGE_SIZE, IMAGE_SIZE),
        interpolation=cv2.INTER_LINEAR
    )

    return np.ascontiguousarray(
        frame_resized,
        dtype=np.uint8
    )


def extract_frame_indices(
    video_path,
    indices
):
    """
    Extract explicit source-video frame indices.
    """

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open video: {video_path}"
        )

    frame_count = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    frames = []
    actual_indices = []

    for index in indices:

        index = int(index)

        if index < 0:
            continue

        if index >= frame_count:
            index = frame_count - 1

        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            index
        )

        ret, frame = cap.read()

        if not ret:
            continue

        frames.append(
            prepare_frame(frame)
        )

        actual_indices.append(index)

    cap.release()

    return frames, actual_indices


# ======================================================================
# Fixed frame-count sampling
# ======================================================================

def extract_num_frames(
    video_path,
    num_frames
):
    """
    Extract num_frames evenly distributed across the entire video.

    Useful for standalone testing and for conditions that require a
    fixed number of observations.
    """

    info = get_video_info(video_path)

    frame_count = info["frame_count"]

    if num_frames <= 0:
        raise ValueError(
            "--num-frames must be greater than zero"
        )

    num_frames = min(
        num_frames,
        frame_count
    )

    indices = np.linspace(
        0,
        frame_count - 1,
        num_frames
    )

    indices = np.round(
        indices
    ).astype(int)

    indices = list(
        dict.fromkeys(
            indices.tolist()
        )
    )

    frames, actual_indices = (
        extract_frame_indices(
            video_path,
            indices
        )
    )

    timestamps = [
        index / info["source_fps"]
        for index in actual_indices
    ]

    return frames, timestamps


# ======================================================================
# FPS sampling
# ======================================================================

def extract_at_sample_fps(
    video_path,
    sample_fps
):
    """
    Sample the complete video at the requested temporal rate.

    Example:

        --sample-fps 5

    requests observations approximately every 0.2 seconds.

    This is the sampling mode used by Experiment A.
    """

    if sample_fps <= 0:
        raise ValueError(
            "--sample-fps must be greater than zero"
        )

    info = get_video_info(video_path)

    source_fps = info["source_fps"]
    duration = info["duration"]

    timestamps = np.arange(
        0.0,
        duration,
        1.0 / sample_fps
    ).tolist()

    indices = [
        round(timestamp * source_fps)
        for timestamp in timestamps
    ]

    indices = [
        min(
            index,
            info["frame_count"] - 1
        )
        for index in indices
    ]

    # Remove duplicate source frames while preserving order.
    unique_indices = []
    seen = set()

    for index in indices:

        if index in seen:
            continue

        seen.add(index)
        unique_indices.append(index)

    frames, actual_indices = (
        extract_frame_indices(
            video_path,
            unique_indices
        )
    )

    actual_timestamps = [
        index / source_fps
        for index in actual_indices
    ]

    return frames, actual_timestamps


# ======================================================================
# Explicit timestamp sampling
# ======================================================================

def extract_at_timestamps(
    video_path,
    timestamps
):
    """
    Extract the source frames nearest to explicit timestamps.

    Used by Experiment C for single-frame and sparse-frame conditions.
    """

    info = get_video_info(video_path)

    source_fps = info["source_fps"]
    frame_count = info["frame_count"]

    indices = []

    for timestamp in timestamps:

        timestamp = float(timestamp)

        if timestamp < 0:
            raise ValueError(
                f"Negative frame timestamp: {timestamp}"
            )

        index = round(
            timestamp * source_fps
        )

        index = min(
            index,
            frame_count - 1
        )

        indices.append(index)

    frames, actual_indices = (
        extract_frame_indices(
            video_path,
            indices
        )
    )

    actual_timestamps = [
        index / source_fps
        for index in actual_indices
    ]

    return frames, actual_timestamps


# ======================================================================
# Evidence interval sampling
# ======================================================================

def extract_from_intervals(
    video_path,
    intervals,
    sample_fps
):
    """
    Sample frames only from supplied evidence intervals.

    Used by Experiment B and interval-based Experiment C conditions.
    """

    if sample_fps <= 0:
        raise ValueError(
            "--sample-fps must be greater than zero"
        )

    info = get_video_info(video_path)

    source_fps = info["source_fps"]
    frame_count = info["frame_count"]
    duration = info["duration"]

    requested_indices = []

    for interval in intervals:

        if (
            not isinstance(interval, list)
            or len(interval) != 2
        ):
            raise ValueError(
                f"Invalid evidence interval: {interval}"
            )

        start = float(interval[0])
        end = float(interval[1])

        if start < 0:
            raise ValueError(
                f"Negative interval start: {start}"
            )

        if end < start:
            raise ValueError(
                f"Interval end before start: {interval}"
            )

        start = min(
            start,
            duration
        )

        end = min(
            end,
            duration
        )

        interval_timestamps = np.arange(
            start,
            end,
            1.0 / sample_fps
        ).tolist()

        # Ensure very short intervals still contribute at least one
        # observation.
        if not interval_timestamps:
            interval_timestamps = [start]

        for timestamp in interval_timestamps:

            index = round(
                timestamp * source_fps
            )

            index = min(
                index,
                frame_count - 1
            )

            requested_indices.append(index)

    # Remove duplicate source frames while preserving temporal order.
    unique_indices = []
    seen = set()

    for index in requested_indices:

        if index in seen:
            continue

        seen.add(index)
        unique_indices.append(index)

    frames, actual_indices = (
        extract_frame_indices(
            video_path,
            unique_indices
        )
    )

    actual_timestamps = [
        index / source_fps
        for index in actual_indices
    ]

    return frames, actual_timestamps


# ======================================================================
# Model and processor
# ======================================================================

def load_model_and_processor(
    model_path=DEFAULT_MODEL_PATH
):
    """
    Load the native Cosmos3 Edge multimodal processor and model.
    """

    print(
        f"Loading Cosmos3 Edge processor from "
        f"{model_path}..."
    )

    processor = AutoProcessor.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=True
    )

    print(
        f"Processor type: "
        f"{type(processor).__name__}"
    )

    print(
        f"Loading Cosmos3 Edge model from "
        f"{model_path}..."
    )

    model = (
        AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.float16,
            #device_map="auto",
            device_map={"": "cuda:0"},
            trust_remote_code=True,
            local_files_only=True
        )
    )

    print("Model loaded.")
    print(f"Model device: {model.device}")

    return processor, model


# ======================================================================
# Multimodal input construction
# ======================================================================

def build_messages(
    prompt_text,
    frames,
    frame_timestamps
):
    """
    Construct the Cosmos3 Edge multimodal conversation.

    Each selected frame is paired with its actual timestamp on the
    original video timeline. This gives Cosmos3 explicit temporal
    grounding while preserving externally controlled frame sampling.
    """

    if len(frames) != len(frame_timestamps):
        raise ValueError(
            "Number of frames does not match number "
            "of frame timestamps: "
            f"{len(frames)} frames vs "
            f"{len(frame_timestamps)} timestamps"
        )

    content = []

    for frame_np, timestamp in zip(
        frames,
        frame_timestamps
    ):
        # Put the timestamp immediately before the image it describes.
        # Use a fixed precision so the model sees the exact observation
        # time in a consistent format.
        content.append(
            {
                "type": "text",
                "text": (
                    f"Video frame timestamp: "
                    f"{float(timestamp):.3f} seconds"
                )
            }
        )

        content.append(
            {
                "type": "image",
                "image": frame_np
            }
        )

    content.append(
        {
            "type": "text",
            "text": prompt_text
        }
    )

    return [
        {
            "role": "user",
            "content": content
        }
    ]

def build_inputs(
    processor,
    prompt_text,
    frames,
    frame_timestamps
):
    """
    Build Cosmos3 multimodal model inputs.

    Frames are externally selected according to the experimental
    condition, and each frame is explicitly grounded to its timestamp
    on the original video timeline.
    """

    messages = build_messages(
        prompt_text,
        frames,
        frame_timestamps
    )

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt"
    )

    return inputs


# ======================================================================
# Inference
# ======================================================================

def move_inputs_to_device(
    inputs,
    device
):
    """
    Move processor tensors to the model's primary device while leaving
    non-tensor metadata unchanged.
    """

    moved = {}

    for key, value in inputs.items():

        if torch.is_tensor(value):
            moved[key] = value.to(device)
        else:
            moved[key] = value

    return moved


def run_inference(
    model,
    processor,
    inputs
):
    """
    Generate and decode only the newly generated assistant tokens.
    """

    inputs = move_inputs_to_device(
        inputs,
        model.device
    )

    input_length = (
        inputs["input_ids"].shape[1]
    )

    print(
        f"Input token count: {input_length}"
    )

    with torch.inference_mode():

        output = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False
        )

    output_length = output.shape[1]

    print(
        f"Output token count: {output_length}"
    )

    # For decoder-style generation, model.generate() returns the input
    # sequence followed by newly generated tokens. Decode only the new
    # portion so the experiment runner receives the model answer rather
    # than the entire system/user prompt.
    generated_tokens = output[
        :,
        input_length:
    ]

    response_text = processor.batch_decode(
        generated_tokens,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0]

    return response_text.strip()


# ======================================================================
# Output
# ======================================================================

def save_output(
    video_path,
    response_text
):
    """
    Preserve the standalone output-file behavior of the earlier script.
    """

    model_name = "cosmos3_edge"

    output_dir = (
        f"/workspace/output/{model_name}"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    basename = os.path.splitext(
        os.path.basename(
            video_path
        )
    )[0]

    output_file = os.path.join(
        output_dir,
        (
            f"{basename}_"
            f"{model_name}_"
            f"{timestamp}.txt"
        )
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(response_text)

    return output_file


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Cosmos3 Edge video inference"
        )
    )

    parser.add_argument(
        "--video-path",
        required=True,
        help="Path to video file"
    )

    parser.add_argument(
        "--question",
        required=True,
        help="Prompt/question for Cosmos3 Edge"
    )

    # ------------------------------------------------------------------
    # Mutually exclusive evidence-selection modes
    # ------------------------------------------------------------------

    sampling = (
        parser.add_mutually_exclusive_group()
    )

    sampling.add_argument(
        "--num-frames",
        type=int,
        default=None,
        help=(
            "Extract a fixed number of evenly spaced "
            "frames from the entire video"
        )
    )

    sampling.add_argument(
        "--frame-timestamps",
        default=None,
        help=(
            "JSON list of explicit frame timestamps, "
            'for example "[1.0,3.5,5.0]"'
        )
    )

    sampling.add_argument(
        "--evidence-intervals",
        default=None,
        help=(
            "JSON list of temporal evidence intervals, "
            'for example "[[2.0,4.0],[7.0,9.0]]"'
        )
    )

    # sample-fps is separate because it serves two purposes:
    #
    # 1. Full-video sampling for Experiment A.
    # 2. Sampling inside evidence intervals for Experiments B/C.
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0,
        help=(
            "Sampling rate. With no other sampling mode, "
            "sample the full video at this FPS. When "
            "--evidence-intervals is supplied, sample only "
            "those intervals at this FPS."
        )
    )

    parser.add_argument(
        "--model-path",
        default=DEFAULT_MODEL_PATH,
        help="Local Cosmos3 Edge model directory"
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Determine evidence-selection mode
    # ------------------------------------------------------------------

    if args.frame_timestamps is not None:

        timestamps = json.loads(
            args.frame_timestamps
        )

        if not isinstance(
            timestamps,
            list
        ):
            raise ValueError(
                "--frame-timestamps must contain "
                "a JSON list"
            )

        frames, actual_timestamps = (
            extract_at_timestamps(
                args.video_path,
                timestamps
            )
        )

        sampling_mode = (
            "frame_timestamps"
        )

    elif args.evidence_intervals is not None:

        intervals = json.loads(
            args.evidence_intervals
        )

        if not isinstance(
            intervals,
            list
        ):
            raise ValueError(
                "--evidence-intervals must "
                "contain a JSON list"
            )

        frames, actual_timestamps = (
            extract_from_intervals(
                args.video_path,
                intervals,
                args.sample_fps
            )
        )

        sampling_mode = (
            "evidence_intervals"
        )

    elif args.num_frames is not None:

        frames, actual_timestamps = (
            extract_num_frames(
                args.video_path,
                args.num_frames
            )
        )

        sampling_mode = (
            "num_frames"
        )

    else:

        frames, actual_timestamps = (
            extract_at_sample_fps(
                args.video_path,
                args.sample_fps
            )
        )

        sampling_mode = (
            "sample_fps"
        )

    if not frames:
        raise RuntimeError(
            "No frames were extracted."
        )

    # ------------------------------------------------------------------
    # Report the evidence actually supplied to Cosmos3
    # ------------------------------------------------------------------

    print(
        f"Sampling mode: {sampling_mode}"
    )

    print(
        f"Frames extracted: {len(frames)}"
    )

    print(
        "Frame timestamps:"
    )

    print(
        json.dumps(
            actual_timestamps
        )
    )

    # ------------------------------------------------------------------
    # Load Cosmos3
    # ------------------------------------------------------------------

    processor, model = (
        load_model_and_processor(
            args.model_path
        )
    )

    # ------------------------------------------------------------------
    # Construct native multimodal inputs
    # ------------------------------------------------------------------

    print(
        "Preparing multimodal inputs..."
    )
    grounded_question = (
      "IMPORTANT TEMPORAL GROUNDING INSTRUCTION:\n"
      "Each provided video frame is preceded by its timestamp on the "
      "original video timeline. When referring to time or returning "
      "temporal evidence, use only these provided timestamps. Do not "
      "estimate timestamps between observations.\n\n"
      f"{args.question}"
)

    inputs = build_inputs(
        processor,
        grounded_question,
        frames,
        actual_timestamps
    )

    if "pixel_values" in inputs:

        print(
            "Visual inputs present: yes"
        )

        print(
            f"pixel_values shape: "
            f"{tuple(inputs['pixel_values'].shape)}"
        )

    elif "pixel_values_videos" in inputs:

        print(
            "Visual inputs present: yes"
        )

        print(
            f"pixel_values_videos shape: "
            f"{tuple(inputs['pixel_values_videos'].shape)}"
        )

    else:

        visual_keys = [
            key
            for key in inputs.keys()
            if (
                "pixel" in key.lower()
                or "image" in key.lower()
                or "video" in key.lower()
            )
        ]

        print(
            f"Visual input keys: "
            f"{visual_keys}"
        )

    # ------------------------------------------------------------------
    # Run inference
    # ------------------------------------------------------------------

    print(
        "Running inference..."
    )

    response_text = run_inference(
        model,
        processor,
        inputs
    )

    # ------------------------------------------------------------------
    # Response markers consumed by the experiment runner
    # ------------------------------------------------------------------

    print()
    print(
        "=== Cosmos3 Edge Response ==="
    )

    print(response_text)

    print(
        "=== End Response ==="
    )

    # ------------------------------------------------------------------
    # Save standalone output
    # ------------------------------------------------------------------

    output_file = save_output(
        args.video_path,
        response_text
    )

    print(
        f"Saved Cosmos3 Edge output to: "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()
