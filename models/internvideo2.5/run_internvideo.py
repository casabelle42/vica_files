import os
import sys
import json
import torch
from PIL import Image
from torchvision import transforms
from internvideo2 import build_model

# ---------------------------------------------------------
# Load model once
# ---------------------------------------------------------

model = build_model("internvideo2_1b").cuda().eval()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])

# ---------------------------------------------------------
# Load frames
# ---------------------------------------------------------

def load_clip_frames(clip_dir):
    frames = []
    for fname in sorted(os.listdir(clip_dir)):
        if fname.endswith(".png"):
            img = Image.open(os.path.join(clip_dir, fname)).convert("RGB")
            frames.append(transform(img))
    return frames


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":
    clip_dir = sys.argv[1]

    frames = load_clip_frames(clip_dir)
    clip_tensor = torch.stack(frames, dim=1).unsqueeze(0).cuda()  # (1, C, T, H, W)

    with torch.no_grad():
        features = model(clip_tensor).cpu().numpy().tolist()

    print(json.dumps({"features": features}))
