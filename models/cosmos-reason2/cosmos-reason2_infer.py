#!/usr/bin/env python3
import sys
import torch
import cv2
import numpy as np
from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor

def extract_frames(video_path, max_frames=16):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = torch.linspace(0, frame_count - 1, max_frames).long().tolist()

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize to 448 by 448
        frame_resized = cv2.resize(frame_rgb, (448, 448), interpolation=cv2.INTER_LINEAR)

        # Ensure NumPy uint8
        frame_np = np.ascontiguousarray(frame_resized, dtype=np.uint8)

        frames.append(frame_np)

    cap.release()
    return frames


def main():
    if len(sys.argv) < 3:
        print("Usage: cosmos_infer.py <video> <max-frames> \"<question>\"")
        sys.exit(1)

    video = sys.argv[1]
    max_frames = int(sys.argv[2])
    question = sys.argv[3]
    
    model_name = "cosmos_reason2"
    output_dir = f"/workspace/output/{model_name}"
    
    model_path = "/opt/models/cosmos-reason2-8b"
    
    print(f"Loading model from {model_path}...")
    processor = Qwen3VLProcessor.from_pretrained(model_path, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    #print([t for t in processor.tokenizer.get_vocab().keys() if "image" in t])
    
    print(f"Extracting {max_frames} frames from {video}...")
    frames_np = extract_frames(video, max_frames)
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "video", "video": video},
                {
                    "type": "text",
                    "text": (
                        question
                    )
                },
            ],
        }
    ]

    prompt = processor.apply_chat_template(
        messages,
        add_generation_prompt=True
    )
 
    print("Preparing inputs...")
    inputs = processor(
        text=prompt,
        videos=frames_np,
        return_tensors="pt"
    ).to("cuda")
    

    print("Running inference...")
    output = model.generate(
        **inputs,
        max_new_tokens=600,
        do_sample=False
    )

    result = processor.decode(output[0], skip_special_tokens=True)
    print("\n=== Cosmos-Reason2 Result ===\n")
    print(result)
    
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.splitext(os.path.basename(args.video))[0]
    output_file = os.path.join(output_dir, f"{basename}_{model_name}_{timestamp}.txt")

    # Save output
    with open(output_file, "w") as f:
        f.write(response_text)

    # Optional: print the path so the wrapper can show it
    print(f"Saved Cosmos-Reason2 output to: {output_file}")

if __name__ == "__main__":
    main()
