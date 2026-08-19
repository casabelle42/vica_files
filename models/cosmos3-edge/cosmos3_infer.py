import json
import torch
import argparse
import cv2
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer


def extract_frames(video_path, max_frames=16):
    """
    Extract evenly spaced frames from a video, resize to 448x448,
    convert to RGB uint8 numpy arrays.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 0:
        raise RuntimeError(f"Video has no frames: {video_path}")

    indices = torch.linspace(0, frame_count - 1, max_frames).long().tolist()

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # BGR ? RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize to 448x448 (Cosmos-3 Edge vision encoder resolution)
        frame_resized = cv2.resize(frame_rgb, (448, 448), interpolation=cv2.INTER_LINEAR)

        # Ensure contiguous uint8 numpy array
        frame_np = np.ascontiguousarray(frame_resized, dtype=np.uint8)

        frames.append(frame_np)

    cap.release()
    return frames


def load_model_and_tokenizer(model_path="/opt/models/cosmos3-edge/"):
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        local_files_only=True
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

    return tokenizer, model


def build_messages(prompt_text, frames):
    """
    Build Cosmos-3 Edge multimodal message list:
    - One user message
    - Text prompt
    - Frames as numpy arrays
    """
    content = [{"type": "text", "text": prompt_text}]

    for frame_np in frames:
        content.append({"type": "image", "image": frame_np})

    return [{"role": "user", "content": content}]


def build_prompt(tokenizer, messages):
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )


def run_inference(model, tokenizer, prompt):
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    output = model.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.2,
        do_sample=False
    )

    return tokenizer.decode(output[0], skip_special_tokens=True)


def save_output_json(path, response_text):
    with open(path, "w") as f:
        json.dump({"response": response_text}, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--num_frames", type=int, default=16, help="Number of frames to extract")
    parser.add_argument("--prompt", required=True, help="Text prompt for the model")
    args = parser.parse_args()
    
    model_name = "cosmos3_edge"
    output_dir = f"/workspace/output/{model_name}"

    # Load model + tokenizer
    tokenizer, model = load_model_and_tokenizer()

    # Extract frames
    frames = extract_frames(args.video, max_frames=args.num_frames)

    # Build multimodal messages
    messages = build_messages(args.prompt, frames)

    # Apply chat template
    prompt = build_prompt(tokenizer, messages)

    # Run inference
    response_text = run_inference(model, tokenizer, prompt)

    # Save output
    # Build output path

    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.splitext(os.path.basename(args.video))[0]
    output_file = os.path.join(output_dir, f"{basename}_{model_name}_{timestamp}.txt")

    # Save output
    with open(output_file, "w") as f:
        f.write(response_text)

    # Optional: print the path so the wrapper can show it
    print(f"Saved Cosmos-3 Edge output to: {output_file}")


if __name__ == "__main__":
    main()
