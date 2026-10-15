#!/usr/bin/env python3
"""Offline InternVideo2.5 inference on NVIDIA Thor.

Usage:
 python3 internvideo2_5_infer.py --video-path /workspace/videos/example.MOV --max-frames 8 --question 'What happens?'
 python3 internvideo2_5_infer.py --input-path /workspace/image.jpg --question 'Describe this image.'
"""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image
import torch
from torchvision import transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer

MODEL_PATH = '/opt/models/InternVideo2_5_Chat_8B'
TOKENIZER_PATH = '/opt/models/internvideo_tokenizer_test'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}


def transform_image(size):
    return T.Compose([
        T.Lambda(lambda image: image.convert('RGB')),
        T.Resize((size, size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
    ])


def read_video(path, max_frames, size, sample_fps=None, frame_timestamps=None, evidence_intervals=None):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f'Cannot open video: {path}')
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if count <= 0:
            raise RuntimeError(f'Video contains no readable frames: {path}')
        if frame_timestamps is not None:
            if fps <= 0:
                raise RuntimeError('Source FPS unavailable for timestamp selection')
            indices = np.array([min(count - 1, max(0, round(t * fps)))
                                for t in frame_timestamps], dtype=int)
        elif evidence_intervals is not None:
            if fps <= 0:
                raise RuntimeError('Source FPS unavailable for interval selection')
            if sample_fps is None:
                raise RuntimeError('--sample-fps required for interval selection')
            times = []
            for start, end in evidence_intervals:
                times.extend(np.arange(start, end, 1.0 / sample_fps).tolist())
            indices = np.unique(np.clip(np.rint(np.asarray(times) * fps).astype(int), 0, count - 1))
        elif sample_fps is not None:
            if fps <= 0:
                raise RuntimeError('Cannot sample by FPS: source FPS unavailable')
            times = np.arange(0, count / fps, 1.0 / sample_fps)
            indices = np.unique(np.clip(np.rint(times * fps).astype(int), 0, count - 1))
        else:
            indices = np.linspace(0, count - 1, min(max_frames, count), dtype=int)
        if len(indices) == 0:
            raise RuntimeError('Evidence selection yielded no frames')
        convert = transform_image(size)
        tensors = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f'Could not decode frame {index} in {path}')
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tensors.append(convert(Image.fromarray(rgb)))
        print(f'Video FPS: {fps:.2f}; total frames: {count}; sampled: {len(tensors)}', file=sys.stderr, flush=True)
        return torch.stack(tensors), [int(i) / fps for i in indices], fps, count, [int(i) for i in indices]
    finally:
        capture.release()


def main():
    parser = argparse.ArgumentParser(description='InternVideo2.5 LAS-VICA experiment inference')
    parser.add_argument('--video-path', '--input-path', dest='input_path', type=Path, required=True)
    sampling = parser.add_mutually_exclusive_group()
    sampling.add_argument('--sample-fps', type=float, default=None)
    sampling.add_argument('--max-frames', type=int, default=None)
    evidence = parser.add_mutually_exclusive_group()
    evidence.add_argument('--frame-timestamps', type=json.loads)
    evidence.add_argument('--evidence-intervals', type=json.loads)
    parser.add_argument('--question', required=True)
    parser.add_argument('--max-new-tokens', type=int, default=256)
    parser.add_argument('--image-size', type=int, default=448)
    parser.add_argument('--model-path', default=MODEL_PATH)
    parser.add_argument('--tokenizer-path', default=TOKENIZER_PATH)
    args = parser.parse_args()
    if not args.input_path.is_file():
        parser.error(f'Input not found: {args.input_path}')
    if args.sample_fps is not None and args.sample_fps <= 0:
        parser.error('--sample-fps must be positive')
    if args.max_frames is not None and args.max_frames <= 0:
        parser.error('--max-frames must be positive')
    if args.max_new_tokens <= 0 or args.image_size <= 0:
        parser.error('max-new-tokens and image-size must be positive')
    if args.frame_timestamps is not None:
        if not isinstance(args.frame_timestamps, list) or not args.frame_timestamps or any(
            not isinstance(t, (int, float)) or not np.isfinite(t) or t < 0 for t in args.frame_timestamps
        ):
            parser.error('--frame-timestamps must be a nonempty JSON array of nonnegative numbers')
    if args.evidence_intervals is not None:
        if not isinstance(args.evidence_intervals, list) or not args.evidence_intervals or any(
            not isinstance(pair, list) or len(pair) != 2 or
            not all(isinstance(t, (int, float)) and np.isfinite(t) for t in pair) or
            pair[0] < 0 or pair[1] <= pair[0] for pair in args.evidence_intervals
        ):
            parser.error('--evidence-intervals must be a nonempty JSON array of [start,end] pairs')
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path, trust_remote_code=True,
        local_files_only=True, use_fast=False)
    model = AutoModel.from_pretrained(args.model_path, torch_dtype=torch.bfloat16,
        trust_remote_code=True, local_files_only=True, low_cpu_mem_usage=True,
        attn_implementation='eager').eval().cuda()
    if args.input_path.suffix.lower() in IMAGE_EXTENSIONS:
        with Image.open(args.input_path) as image:
            pixels = transform_image(args.image_size)(image).unsqueeze(0)
        count = 1
        timestamps = []
        padding_count = 0
        source_fps = None
        total_source_frames = None
    else:
        pixels, timestamps, source_fps, total_source_frames, source_indices = read_video(
            args.input_path, args.max_frames or 8,
            args.image_size, sample_fps=args.sample_fps,
            frame_timestamps=args.frame_timestamps,
            evidence_intervals=args.evidence_intervals)
        sampled_count = len(timestamps)
        sampled_timestamps = timestamps.copy()
        group_size = int(model.local_num_frames)
        if group_size < 1:
            raise RuntimeError(f'Invalid model.local_num_frames: {group_size}')
        padding_count = (-sampled_count) % group_size
        if padding_count:
            # Repeat final sampled frame; never discard real sampled evidence.
            pixels = torch.cat((pixels, pixels[-1:].repeat(padding_count, 1, 1, 1)), dim=0)
            timestamps.extend([timestamps[-1]] * padding_count)
        count = pixels.shape[0]
        metadata = {
            'sample_fps_requested': args.sample_fps,
            'max_frames_requested': args.max_frames,
            'source_fps': source_fps,
            'source_frame_count': total_source_frames,
            'sampled_frames': sampled_count,
            'padded_frames': padding_count,
            'frames_sent_to_model': count,
            'temporal_group_size': group_size,
            'frame_timestamps_seconds': timestamps,
            'padded_frame_mask': [False] * sampled_count + [True] * padding_count,
        }
        print('Frame timestamps:', file=sys.stdout, flush=True)
        print(json.dumps(sampled_timestamps), file=sys.stdout, flush=True)
        print('Source frame indices:', file=sys.stdout, flush=True)
        print(json.dumps(source_indices), file=sys.stdout, flush=True)
        print(f'Frames extracted: {sampled_count}', file=sys.stdout, flush=True)
        print('INTERNVIDEO2_5_SAMPLING_METADATA=' + json.dumps(metadata),
              file=sys.stderr, flush=True)
    pixels = pixels.to(device='cuda', dtype=torch.bfloat16)
    prompt = ''.join(f'Frame{i+1}: <image>\n' for i in range(count)) + args.question
    with torch.inference_mode():
        response = model.chat(tokenizer=tokenizer, pixel_values=pixels,
            question=prompt, generation_config={'max_new_tokens': args.max_new_tokens,
            'do_sample': False}, num_patches_list=[1] * count)
    print('\n=== InternVideo2.5 Response ===')
    print(response)
    print('=== End Response ===')


if __name__ == '__main__':
    main()
