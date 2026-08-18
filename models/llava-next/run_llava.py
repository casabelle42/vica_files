from transformers import AutoProcessor, AutoModelForVision2Seq
import torch
import av
import sys

MODEL_PATH = "/models/LLaVA-NeXT-Video-7B-hf"

processor = AutoProcessor.from_pretrained(MODEL_PATH)
model = AutoModelForVision2Seq.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.float16,
    device_map="auto"
)

def load_video_frames(path):
    container = av.open(path)
    return [frame.to_image() for frame in container.decode(video=0)]

if __name__ == "__main__":
    video_path = sys.argv[1]
    prompt = " ".join(sys.argv[2:])

    frames = load_video_frames(video_path)
    inputs = processor(text=prompt, videos=frames, return_tensors="pt").to(model.device)
    output = model.generate(**inputs, max_new_tokens=200)
    print(processor.decode(output[0], skip_special_tokens=True))
