#!/usr/bin/env python3
import argparse
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText
import av

def main():
    ap = argparse.ArgumentParser(description="LLaVA inference (prints answer).")
    ap.add_argument("--video_path", required=True, help="Path to input image")
    ap.add_argument("--prompt", required=True, help="Text prompt / question")
    ap.add_argument("--max_new_tokens", type=int, default=128)
    args = ap.parse_args()

    model_id = "llava-hf/LLaVA-NeXT-Video-7B-hf"

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id,
        torch_dtype="auto",
        device_map="auto",
        trust_remote_code=True,
    )
    container = av.open(args.video_path)
    #img = Image.open(args.image).convert("RGB")
    frames = []
    for frame in container.decode(video=0):
      frames.append(frame.to_image())
    print(len(frames))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "video"},
                {"type": "text", "text": args.prompt},
            ],
        }
    ]

    prompt_text = processor.apply_chat_template(messages, add_generation_prompt=True)

    inputs = processor(
        text=prompt_text,
        images=frames,
        return_tensors="pt").to("cuda")

    #if torch.cuda.is_available():
    #    inputs = {k: v.to("cuda") for k, v in inputs.items()}

    out = model.generate(**inputs, max_new_tokens=args.max_new_tokens)

    text = processor.decode(out[0], skip_special_tokens=True)
    print(text)

if __name__ == "__main__":
    main()
