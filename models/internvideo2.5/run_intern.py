import torch
import cv2
import numpy as np
from PIL import Image
from transformers import AutoModel, AutoTokenizer
import argparse


# -------------------------
# Load Video Frames (OpenCV)
# -------------------------
def load_frames_cv2(video_path, max_frames=16):
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(total // max_frames, 1)

    frames = []
    idx = 0

    while cap.isOpened() and len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if idx % step == 0:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(frame))

        idx += 1

    cap.release()
    return frames

# -------------------------
# Preprocess (simple version)
# -------------------------
def preprocess_frames(frames):
    processed = []
    for img in frames:
        img = img.resize((224, 224))
        arr = np.array(img).astype(np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
        processed.append(arr)

    tensor = torch.tensor(processed)
    return tensor



def main(args):

  window_sec = 2.0
  stride_sec = 1.0

  video_path = args.video_path
  model_path = args.model_path
  query_filename = args.query_filename
  max_tokens = args.max_tokens
  save_filename = args.save_filename
  
  # -------------------------
  # Load Model
  # -------------------------
  
  print("Loading model...")
  
  tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
  model = AutoModel.from_pretrained(
      model_path,
      trust_remote_code=True
  ).to("cuda").to(torch.bfloat16)
  
  print("Model loaded")
  
  # -------------------------
  # Run Inference
  # -------------------------
  
  
  print("Loading video...")
  frames = load_frames_cv2(video_path, max_frames=16)
  print(f"Loaded {len(frames)} frames")
  
  pixel_values = preprocess_frames(frames)
  pixel_values = pixel_values.to(torch.bfloat16).to("cuda")
  
  # Required structure
  num_patches_list = [1] * len(frames)
  
  video_prefix = "".join([f"Frame{i+1}: <image>\n" for i in range(len(frames))])
  
  with open(query_filename, "r") as query_f:
    query = query_f.read()
  
  print(query)
    
  question = video_prefix + query #QUERY HERE
   
  print("Running inference...")
  
  with torch.no_grad():
      output, _ = model.chat(
          tokenizer,
          pixel_values,
          question,
          dict(max_new_tokens=max_tokens),
          num_patches_list=num_patches_list,
          history=None,
          return_history=True
      )
  
  print("\nModel Output:")
  print(output)
  with open(save_filename, "w") as writefile:
    writefile.write(f"{output}\n")

if __name__ == "__main__":
  # 1. Initialize the parser
  parser = argparse.ArgumentParser(description="script that runs internvideo2, requests a video and text prompt and then returns a report.")
  
  # 2. Add arguments
  parser.add_argument("--video_path", default="test.mp4", help="/path/to/video ex: test.mp4")
  
  # Optional argument with a default value
  parser.add_argument("--model_path", default="OpenGVLab/InternVideo2_5_Chat_8B", help="/path/to/model ex: OpenGVLab/InternVideo2_5_Chat_8B")

  # Optional argument with a default value
  parser.add_argument("--query_filename", default="query.txt", help="/path/to/query_filename: query.txt")
  
  # Optional argument with a default value
  parser.add_argument("--max_tokens", type=int, default=128, help="max number of characters returned ex: 128") 
   
  # Optional argument with a default value
  parser.add_argument("--save_filename", default="internvideo2_report.txt", help="name for text file for output ex: internvideo2_report.txt")
  
  # 3. Parse the arguments
  args = parser.parse_args()
  
  main(args)