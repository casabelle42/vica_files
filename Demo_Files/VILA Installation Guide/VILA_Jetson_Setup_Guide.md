# VILA Setup Guide for Jetson Orin Nano

This guide provides step-by-step instructions to set up and run VILA (Vision-Language Model) on Jetson Orin Nano devices.

## Prerequisites

- Jetson Orin Nano with JetPack 6.1+ (L4T R36.4.7)
- At least 7.4GB RAM
- Camera connected to `/dev/video0`
- Docker installed and running
- Internet connection for model downloads

## System Requirements

- **JetPack Version**: 6.1+ (L4T R36.4.7)
- **RAM**: 7.4GB (shared between CPU and GPU)
- **Storage**: At least 20GB free space for models
- **Camera**: USB camera or built-in camera

## Step 1: System Setup and Memory Optimization

### 1.1 Check System Specifications
```bash
# Check JetPack version
cat /etc/nv_tegra_release

# Check available memory
free -h

# Check GPU status
nvidia-smi
```

### 1.2 Optimize Swap Memory (Critical for VILA)

#### Disable ZRAM (if present)
```bash
# Check current swap
swapon --show

# Disable ZRAM if active
sudo swapoff -a
sudo systemctl disable nvidia-zram-swap
```

#### Create Large Swap File on NVMe SSD
```bash
# Create 16GB swap file (adjust size as needed)
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap persistent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### Optimize Memory Settings
```bash
# Add to /etc/sysctl.conf for persistent settings
echo 'vm.swappiness=5' | sudo tee -a /etc/sysctl.conf
echo 'vm.vfs_cache_pressure=50' | sudo tee -a /etc/sysctl.conf

# Apply immediately
sudo sysctl -p
```

### 1.3 Verify Memory Configuration
```bash
# Check swap status
swapon --show
free -h

# Verify settings
cat /proc/sys/vm/swappiness
cat /proc/sys/vm/vfs_cache_pressure
```

## Step 2: Docker Configuration (Critical)

### 2.1 Configure Docker Default Runtime
```bash
# Backup existing configuration
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.backup

# Create proper Docker configuration
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
EOF

# Restart Docker service
sudo systemctl restart docker
```

### 2.2 Verify Docker Configuration
```bash
# Check Docker runtime
docker info | grep -i runtime

# Should show: Default Runtime: nvidia
```

## Step 3: Install Jetson Containers

### 3.1 Clone and Install Jetson Containers
```bash
# Clone the repository
git clone https://github.com/dusty-nv/jetson-containers
cd jetson-containers

# Install jetson-containers utilities
bash install.sh
```

### 3.2 Pull NanoLLM Container
```bash
# Pull the nano_llm container
docker pull dustynv/nano_llm:r36.4.0
```

## Step 4: Prepare Data Directory

### 4.1 Create Data Structure
```bash
# Create data directory structure
mkdir -p jetson-containers/data/models/mlc/dist
mkdir -p jetson-containers/data/images
mkdir -p /dev/shm
```

### 4.2 Test Camera Access
```bash
# Check available cameras
ls -la /dev/video*

# Test camera with ffmpeg
ffmpeg -f v4l2 -i /dev/video0 -frames:v 1 -y test_camera.jpg

# Verify image was captured
ls -la test_camera.jpg
```

## Step 5: Run VILA Model

### 5.1 Basic VILA Test (Memory Optimized)
```bash
# Run VILA with optimized memory settings
docker run --runtime nvidia \
    --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    --rm --network host \
    --shm-size=4g \
    --volume $(pwd)/jetson-containers/data:/data \
    dustynv/nano_llm:r36.4.0 \
    python3 -m nano_llm.chat \
    --model Efficient-Large-Model/VILA1.5-3b \
    --api mlc \
    --quantization q4f16_ft \
    --max-context-len 256 \
    --max-new-tokens 32 \
    --prompt "/data/images/test_camera.jpg" \
    --prompt "What do you see?"
```

### 5.2 Live Camera Analysis
```bash
# Run VILA with live camera feed
docker run --runtime nvidia \
    --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    --rm --network host \
    --shm-size=4g \
    --volume $(pwd)/jetson-containers/data:/data \
    --device /dev/video0 \
    dustynv/nano_llm:r36.4.0 \
    python3 -m nano_llm.chat \
    --model Efficient-Large-Model/VILA1.5-3b \
    --api mlc \
    --quantization q4f16_ft \
    --max-context-len 256 \
    --max-new-tokens 32 \
    --prompt "/dev/video0" \
    --prompt "Describe what you see in this video feed"
```

## Step 6: Troubleshooting

### 6.1 Common Issues and Solutions

#### GPU Memory Errors
```bash
# If you see "CUDA: out of memory" errors:
# 1. Reduce context length
--max-context-len 128

# 2. Reduce max tokens
--max-new-tokens 16

# 3. Reduce shared memory
--shm-size=2g
```

#### Docker Runtime Issues
```bash
# If Docker runtime is not nvidia:
# 1. Check configuration
cat /etc/docker/daemon.json

# 2. Restart Docker
sudo systemctl restart docker

# 3. Verify runtime
docker info | grep -i runtime
```

#### Model Loading Issues
```bash
# If model fails to load:
# 1. Check available memory
free -h

# 2. Check GPU status
nvidia-smi

# 3. Clear Docker cache
docker system prune -a
```

### 6.2 Performance Optimization

#### Memory Monitoring
```bash
# Monitor memory usage during model loading
watch -n 1 'free -h && nvidia-smi'
```

#### Model Quantization
```bash
# The model will automatically quantize on first run
# This process takes 5-10 minutes and creates optimized versions
# Quantized models are cached in /data/models/mlc/dist/
```

## Step 7: Advanced Usage

### 7.1 Custom Web Interface
```bash
# Run VILA with web interface
docker run --runtime nvidia \
    --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    --rm --network host \
    --shm-size=4g \
    --volume $(pwd)/jetson-containers/data:/data \
    --device /dev/video0 \
    dustynv/nano_llm:r36.4.0 \
    python3 -m nano_llm.agents.video_query \
    --model Efficient-Large-Model/VILA1.5-3b \
    --api mlc \
    --quantization q4f16_ft \
    --max-context-len 256
```

### 7.2 Batch Image Processing
```bash
# Process multiple images
for image in jetson-containers/data/images/*.jpg; do
    echo "Processing: $image"
    docker run --runtime nvidia \
        --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
        --rm --network host \
        --shm-size=4g \
        --volume $(pwd)/jetson-containers/data:/data \
        dustynv/nano_llm:r36.4.0 \
        python3 -m nano_llm.chat \
        --model Efficient-Large-Model/VILA1.5-3b \
        --api mlc \
        --quantization q4f16_ft \
        --max-context-len 256 \
        --max-new-tokens 32 \
        --prompt "$image" \
        --prompt "Describe this image in detail"
done
```

## Performance Specifications

### Expected Performance
- **Model Loading**: 10-15 seconds (first run), 3-5 seconds (cached)
- **Image Analysis**: 1-3 seconds per image
- **Memory Usage**: ~3-4GB GPU memory
- **Model Size**: 1.3GB (quantized)

### Optimization Tips
1. **First Run**: Model quantization takes 5-10 minutes
2. **Subsequent Runs**: Use cached quantized models
3. **Memory**: Keep other applications closed during VILA usage
4. **Storage**: Ensure 20GB+ free space for models

## Troubleshooting Checklist

- [ ] JetPack 6.1+ installed
- [ ] 16GB swap file created and active
- [ ] Docker default runtime set to nvidia
- [ ] Camera accessible at `/dev/video0`
- [ ] At least 20GB free storage
- [ ] Docker container pulled successfully
- [ ] Data directory structure created
- [ ] GPU accessible via nvidia-smi

## Support and Resources

- **Jetson AI Lab**: https://www.jetson-ai-lab.com/
- **NanoLLM Documentation**: https://dusty-nv.github.io/NanoLLM
- **Jetson Containers**: https://github.com/dusty-nv/jetson-containers
- **VILA Models**: https://huggingface.co/Efficient-Large-Model

## Notes

- This setup is optimized for Jetson Orin Nano with 7.4GB RAM
- VILA models require significant GPU memory
- First run includes model quantization (5-10 minutes)
- Subsequent runs use cached quantized models
- Docker runtime configuration is critical for GPU access
- Swap memory optimization is essential for model loading
