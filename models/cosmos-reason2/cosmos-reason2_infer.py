#!/usr/bin/env python3

import argparse
import json
import os
from datetime import datetime

import cv2
import numpy as np
import torch

from transformers import (
    Qwen3VLForConditionalGeneration,
    Qwen3VLProcessor,
)

from transformers.video_utils import VideoMetadata


# ======================================================================
# Configuration
# ======================================================================

DEFAULT_MODEL_PATH = "/opt/models/cosmos-reason2-8b"
IMAGE_SIZE = 448


# ======================================================================
# Video information
# ======================================================================

def get_video_info(video_path):
    """
    Return metadata for the original source video.
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

    width = int(
        cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    height = int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
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
        "width": width,
        "height": height,
    }


# ======================================================================
# Frame preparation
# ======================================================================

def prepare_frame(frame):
    """
    Convert an OpenCV BGR frame to RGB uint8 and resize it to the
    resolution used by the existing Reason2 pipeline.
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

    Returns both the processed frames and the actual original-video
    indices that were successfully extracted.
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
# Fixed number of frames
# ======================================================================

def extract_num_frames(
    video_path,
    num_frames
):
    """
    Extract a fixed number of evenly spaced observations.

    Returns:
        frames
        timestamps
        source_indices
    """

    info = get_video_info(video_path)

    if num_frames <= 0:
        raise ValueError(
            "--num-frames must be greater than zero"
        )

    num_frames = min(
        num_frames,
        info["frame_count"]
    )

    indices = np.linspace(
        0,
        info["frame_count"] - 1,
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

    return (
        frames,
        timestamps,
        actual_indices
    )


# ======================================================================
# FPS sampling
# ======================================================================

def extract_at_sample_fps(
    video_path,
    sample_fps
):
    """
    Sample the complete source video at the requested experimental
    sampling rate.

    The returned source indices remain indices into the ORIGINAL video.
    They are later supplied to Qwen3-VL through VideoMetadata.
    """

    if sample_fps <= 0:
        raise ValueError(
            "--sample-fps must be greater than zero"
        )

    info = get_video_info(video_path)

    timestamps = np.arange(
        0.0,
        info["duration"],
        1.0 / sample_fps
    ).tolist()

    indices = [
        round(
            timestamp
            * info["source_fps"]
        )
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
        index / info["source_fps"]
        for index in actual_indices
    ]

    return (
        frames,
        actual_timestamps,
        actual_indices
    )


# ======================================================================
# Explicit timestamps
# ======================================================================

def extract_at_timestamps(
    video_path,
    timestamps
):
    """
    Extract observations nearest to explicit timestamps.

    Used for single-frame and sparse-frame experimental conditions.
    """

    info = get_video_info(video_path)

    indices = []

    for timestamp in timestamps:

        timestamp = float(timestamp)

        if timestamp < 0:
            raise ValueError(
                f"Negative timestamp: {timestamp}"
            )

        index = round(
            timestamp
            * info["source_fps"]
        )

        index = min(
            index,
            info["frame_count"] - 1
        )

        indices.append(index)

    frames, actual_indices = (
        extract_frame_indices(
            video_path,
            indices
        )
    )

    actual_timestamps = [
        index / info["source_fps"]
        for index in actual_indices
    ]

    return (
        frames,
        actual_timestamps,
        actual_indices
    )


# ======================================================================
# Evidence intervals
# ======================================================================

def extract_from_intervals(
    video_path,
    intervals,
    sample_fps
):
    """
    Sample only from supplied temporal evidence intervals.

    Used by Experiment B and interval-based Experiment C conditions.
    """

    if sample_fps <= 0:
        raise ValueError(
            "--sample-fps must be greater than zero"
        )

    info = get_video_info(video_path)

    requested_indices = []

    for interval in intervals:

        if (
            not isinstance(interval, list)
            or len(interval) != 2
        ):
            raise ValueError(
                f"Invalid evidence interval: "
                f"{interval}"
            )

        start = float(interval[0])
        end = float(interval[1])

        if start < 0:
            raise ValueError(
                f"Negative interval start: "
                f"{start}"
            )

        if end < start:
            raise ValueError(
                f"Interval end before start: "
                f"{interval}"
            )

        start = min(
            start,
            info["duration"]
        )

        end = min(
            end,
            info["duration"]
        )

        timestamps = np.arange(
            start,
            end,
            1.0 / sample_fps
        ).tolist()

        if not timestamps:
            timestamps = [start]

        for timestamp in timestamps:

            index = round(
                timestamp
                * info["source_fps"]
            )

            index = min(
                index,
                info["frame_count"] - 1
            )

            requested_indices.append(index)

    # Remove duplicates while preserving temporal order.
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
        index / info["source_fps"]
        for index in actual_indices
    ]

    return (
        frames,
        actual_timestamps,
        actual_indices
    )


# ======================================================================
# Model
# ======================================================================

def load_model_and_processor(
    model_path
):
    """
    Load Cosmos-Reason2 and its native Qwen3-VL processor.
    """

    print(
        f"Loading processor from "
        f"{model_path}..."
    )

    processor = (
        Qwen3VLProcessor.from_pretrained(
            model_path,
            trust_remote_code=True,
            local_files_only=True
        )
    )
    processor.video_processor.do_sample_frames = False

    print(
        f"Processor type: "
        f"{type(processor).__name__}"
    )

    print(
        f"Video processor type: "
        f"{type(processor.video_processor).__name__}"
    )

    print(
        f"Loading model from "
        f"{model_path}..."
    )

    model = (
        Qwen3VLForConditionalGeneration
        .from_pretrained(
            model_path,
            dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
            local_files_only=True
        )
    )

    print("Model loaded.")
    print(
        f"Model device: {model.device}"
    )

    return processor, model


# ======================================================================
# Temporal metadata
# ======================================================================

def build_video_metadata(
    frames,
    actual_timestamps
):
    """
    Construct metadata for the already-sampled video supplied to
    Qwen3-VL.

    The processor receives only the selected frames, so metadata indices
    must refer to positions in that supplied frame array, not indices
    from the original source video.
    """

    if len(frames) != len(actual_timestamps):
        raise ValueError(
            "Frame/timestamp count mismatch: "
            f"{len(frames)} frames vs "
            f"{len(actual_timestamps)} timestamps"
        )

    if not frames:
        raise ValueError(
            "Cannot build metadata for an empty video"
        )

    # Determine the effective FPS of the supplied sampled video.
    if len(actual_timestamps) > 1:

        differences = np.diff(
            actual_timestamps
        )

        median_interval = float(
            np.median(differences)
        )

        if median_interval <= 0:
            raise ValueError(
                "Invalid sampled-frame timestamp spacing"
            )

        effective_fps = (
            1.0 / median_interval
        )

    else:
        # A single frame has no meaningful temporal sampling rate.
        # Use 1 FPS as a neutral representation.
        effective_fps = 1.0

    supplied_frame_count = len(frames)

    duration = (
        actual_timestamps[-1]
        - actual_timestamps[0]
    )

    metadata = VideoMetadata(
        total_num_frames=supplied_frame_count,
        fps=effective_fps,
        width=IMAGE_SIZE,
        height=IMAGE_SIZE,
        duration=duration,
        frames_indices=list(
            range(supplied_frame_count)
        )
    )

    return metadata


# ======================================================================
# Prompt / inputs
# ======================================================================

def build_inputs(
    processor,
    question,
    frames,
    video_metadata
):
    """
    Construct the multimodal input from ONLY the frames selected by the
    experimental condition.

    VideoMetadata preserves their positions on the original video
    timeline.
    """

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": frames
                },
                {
                    "type": "text",
                    "text": question
                },
            ],
        }
    ]

    prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = processor(
        text=prompt,
        videos=frames,
        video_metadata=video_metadata,
        return_tensors="pt"
    )

    return inputs


# ======================================================================
# Inference
# ======================================================================

def run_inference(
    model,
    processor,
    inputs
):
    """
    Generate and decode only the newly generated assistant tokens.
    """

    inputs = inputs.to(
        model.device
    )

    input_length = (
        inputs["input_ids"].shape[1]
    )

    print(
        f"Input token count: "
        f"{input_length}"
    )

    with torch.inference_mode():

        output = model.generate(
            **inputs,
            max_new_tokens=600,
            do_sample=False
        )

    generated = output[0][
        input_length:
    ]

    print(
        f"Generated token count: "
        f"{generated.shape[0]}"
    )

    result = processor.decode(
        generated,
        skip_special_tokens=True
    )

    return result.strip()


# ======================================================================
# Main
# ======================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Cosmos-Reason2 video inference"
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
        help="Question or prompt"
    )

    sampling = (
        parser.add_mutually_exclusive_group()
    )

    sampling.add_argument(
        "--num-frames",
        type=int,
        default=None,
        help=(
            "Extract a fixed number of evenly "
            "spaced frames"
        )
    )

    sampling.add_argument(
        "--frame-timestamps",
        default=None,
        help=(
            "JSON list of explicit timestamps"
        )
    )

    sampling.add_argument(
        "--evidence-intervals",
        default=None,
        help=(
            "JSON list of evidence intervals"
        )
    )

    parser.add_argument(
        "--sample-fps",
        type=float,
        default=5.0,
        help=(
            "Sampling rate for the full video "
            "or supplied evidence intervals"
        )
    )

    parser.add_argument(
        "--model-path",
        default=DEFAULT_MODEL_PATH
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Select evidence
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
                "--frame-timestamps must "
                "contain a JSON list"
            )

        (
            frames,
            actual_timestamps,
            source_indices
        ) = extract_at_timestamps(
            args.video_path,
            timestamps
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

        (
            frames,
            actual_timestamps,
            source_indices
        ) = extract_from_intervals(
            args.video_path,
            intervals,
            args.sample_fps
        )

        sampling_mode = (
            "evidence_intervals"
        )

    elif args.num_frames is not None:

        (
            frames,
            actual_timestamps,
            source_indices
        ) = extract_num_frames(
            args.video_path,
            args.num_frames
        )

        sampling_mode = (
            "num_frames"
        )

    else:

        (
            frames,
            actual_timestamps,
            source_indices
        ) = extract_at_sample_fps(
            args.video_path,
            args.sample_fps
        )

        sampling_mode = (
            "sample_fps"
        )

    if not frames:
        raise RuntimeError(
            "No frames were extracted."
        )

    if len(frames) != len(source_indices):
        raise RuntimeError(
            "Frame/source-index count mismatch: "
            f"{len(frames)} frames vs "
            f"{len(source_indices)} indices"
        )

    # ------------------------------------------------------------------
    # Report actual evidence supplied
    # ------------------------------------------------------------------

    print(
        f"Sampling mode: "
        f"{sampling_mode}"
    )

    print(
        f"Frames extracted: "
        f"{len(frames)}"
    )

    print(
        "Frame timestamps:"
    )

    print(
        json.dumps(
            actual_timestamps
        )
    )

    print(
        "Source frame indices:"
    )

    print(
        json.dumps(
            source_indices
        )
    )

    # ------------------------------------------------------------------
    # Build temporal metadata
    # ------------------------------------------------------------------

    video_metadata = (
        build_video_metadata(
            frames,
            actual_timestamps
        )
    )

    print(
        "Video metadata:"
    )

    print(
        f"  total_num_frames: "
        f"{video_metadata.total_num_frames}"
    )

    print(
        f"  source_fps: "
        f"{video_metadata.fps}"
    )

    print(
        f"  duration: "
        f"{video_metadata.duration}"
    )

    print(
        f"  selected_frames: "
        f"{len(video_metadata.frames_indices)}"
    )

    # ------------------------------------------------------------------
    # Load model
    # ------------------------------------------------------------------

    processor, model = (
        load_model_and_processor(
            args.model_path
        )
    )

    # ------------------------------------------------------------------
    # Build inputs
    # ------------------------------------------------------------------

    print(
        "Preparing temporally grounded inputs..."
    )

    inputs = build_inputs(
        processor,
        args.question,
        frames,
        video_metadata
    )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    print(
        "Running inference..."
    )

    result = run_inference(
        model,
        processor,
        inputs
    )

    # ------------------------------------------------------------------
    # Response markers expected by experiment scripts
    # ------------------------------------------------------------------

    print()
    print(
        "=== Cosmos-Reason2 Response ==="
    )

    print(result)

    print(
        "=== End Response ==="
    )

    # ------------------------------------------------------------------
    # Save standalone result
    # ------------------------------------------------------------------

    model_name = "cosmos-reason2"

    output_dir = (
        f"/workspace/output/"
        f"{model_name}"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    timestamp = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    basename = os.path.splitext(
        os.path.basename(
            args.video_path
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

        f.write(result)

    print(
        f"Saved Cosmos-Reason2 output to: "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()