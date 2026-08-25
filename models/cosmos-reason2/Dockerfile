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

# Install Hugging Face Transformers package supporting Cosmos-Reason2
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "transformers>=4.57.0" accelerate torchvision torchcodec \
    opencv-python-headless av

# Create scripts directory
RUN mkdir -p /opt/scripts/cosmos-reason2-8b

# Create models directory
RUN mkdir -p /opt/models/cosmos-reason2-8b/


# Copy your models files to the image
COPY models /opt/models/cosmos-reason2-8b/

# Copy your entrypoint to the image
COPY run_cosmos-reason2_query.sh /opt/scripts/cosmos-reason2-8b/run_cosmos-reason2_query.sh
RUN chmod +x /opt/scripts/cosmos-reason2-8b/run_cosmos-reason2_query.sh

# Pre-download the Cosmos-Reason2 weights directly into the image
# This ensures it runs completely offline without downloading at startup
RUN python3 -c "from transformers import Qwen3VLForConditionalGeneration; \
    Qwen3VLForConditionalGeneration.from_pretrained('/opt/models/cosmos-reason2-8b/', \
    torch_dtype='auto', trust_remote_code=True)"

# Preload processor (optional but recommended)
RUN python3 -c "from transformers import Qwen3VLProcessor; \
    Qwen3VLProcessor.from_pretrained('/opt/models/cosmos-reason2-8b/', \
    trust_remote_code=True)"

#COPY cosmos-reason2_infer.py .

ENTRYPOINT ["/opt/scripts/cosmos-reason2-8b/run_cosmos-reason2_query.sh"]
