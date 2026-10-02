FROM nvcr.io/nvidia/pytorch:25.10-py3

RUN pip install --no-cache-dir \
    "transformers>=4.51.0" \
    accelerate \
    safetensors


# Create models directory
RUN mkdir -p /opt/models/qwen3-14b


# Copy your models files to the image
COPY models /opt/models/qwen3-14b



WORKDIR /workspace