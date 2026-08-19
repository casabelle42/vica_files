# Use NVIDIA's PyTorch ARM64 standard base container for Thor
FROM nvcr.io/nvidia/pytorch:25.10-py3

# Set environment variables for offline execution
ENV DEBIAN_FRONTEND=noninteractive \
    HF_HUB_DISABLE_SYMLINKS=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace



# Install standard dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Install Hugging Face Transformers + multimodal deps
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir git+https://github.com/huggingface/transformers.git

RUN pip install --no-cache-dir accelerate torchvision torchcodec \
    opencv-python-headless av safetensors pillow
    

# Create scripts directory
RUN mkdir -p /opt/scripts/cosmos3-edge

# Create models directory
RUN mkdir -p /opt/models/cosmos3-edge

# Copy your Cosmos-3 Edge model files into the image
COPY model /opt/models/cosmos3-edge/

# Copy your query script (same pattern as Reason2)
COPY run_cosmos3_query.sh /opt/scripts/cosmos3-edge/run_cosmos3_query.sh
RUN chmod +x /opt/scripts/cosmos3-edge/run_cosmos3_query.sh

# Copy your inference logic
#COPY cosmos3_infer.py /opt/scripts/cosmos3-edge/cosmos3_infer.py

# Preload the Cosmos-3 Edge model into the image
# This ensures fully offline execution


ENTRYPOINT ["/opt/scripts/cosmos3-edge/run_cosmos3_query.sh"]