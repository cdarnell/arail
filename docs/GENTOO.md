# Gentoo Linux — OGLab Setup

Full walkthrough for running OGLab on a Gentoo system with local AI inference.

---

## 1. Base System Requirements

```bash
# Python 3.10+
emerge -av dev-lang/python

# pip / venv
emerge -av dev-python/pip dev-python/virtualenv

# Build essentials (needed to compile native wheels)
emerge -av sys-devel/gcc sys-devel/make dev-build/cmake
```

## 2. GPU — Nvidia (CUDA)

### Kernel Config

Enable these in `make menuconfig`:

```
Device Drivers --->
  Graphics support --->
    <M> Direct Rendering Manager (DRM)
    < > Nouveau (disable if using proprietary driver)
```

### Nvidia Drivers

```bash
# Accept the license
echo "x11-drivers/nvidia-drivers NVIDIA-r2" >> /etc/portage/package.license/nvidia

# Install
emerge -av x11-drivers/nvidia-drivers

# Load the module
modprobe nvidia

# Verify
nvidia-smi
```

### CUDA Toolkit

```bash
# USE flags
echo 'dev-util/nvidia-cuda-toolkit -profiler' >> /etc/portage/package.use/cuda

emerge -av dev-util/nvidia-cuda-toolkit

# Verify
nvcc --version
```

### PyTorch with CUDA

```bash
# Inside your OGLab venv:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Verify
python3 -c "import torch; print(torch.cuda.is_available())"
```

## 3. GPU — AMD (ROCm)

```bash
emerge -av dev-libs/rocm-opencl-runtime

# PyTorch ROCm:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0
```

## 4. CPU-Only (No GPU)

```bash
# llama.cpp backend — compiles from source, no GPU needed
pip install llama-cpp-python

# Download a GGUF model
huggingface-cli download \
  TheBloke/Mistral-7B-Instruct-v0.2-GGUF \
  mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  --local-dir ./models
```

## 5. OGLab Setup

```bash
git clone https://github.com/cdarnell/minimalist-blueprint.git oglab
cd oglab
./setup.sh          # auto-detects Gentoo + GPU
source .venv/bin/activate
python3 examples/peanut_farmer/run.py
```

## 6. Airgapped Operation

Once models are downloaded, OGLab runs with zero network:

```bash
# Ensure OGLAB_MODE=airgapped in .env (default)
# All inference is local

# Verify no outbound connections
ss -tunap | grep python   # should show only localhost
```

## 7. Running as a Service (OpenRC)

Create `/etc/init.d/oglab`:

```bash
#!/sbin/openrc-run

name="oglab"
description="OGLab AI inference server"
command="/path/to/oglab/.venv/bin/python3"
command_args="-m vllm.entrypoints.openai.api_server --model ./models/Mistral-7B --port 8000"
directory="/path/to/oglab"
pidfile="/run/${RC_SVCNAME}.pid"
command_background="yes"

depend() {
    need net
}
```

```bash
chmod +x /etc/init.d/oglab
rc-update add oglab default
rc-service oglab start
```

## 8. Recommended Portage USE Flags

```bash
# /etc/portage/make.conf additions for ML workloads
USE="cuda opencl python"
PYTHON_TARGETS="python3_12"
```

## 9. Kernel Tuning for ML

```
# Increase shared memory (needed for large models)
echo "kernel.shmmax = 68719476736" >> /etc/sysctl.conf
sysctl -p

# Huge pages (vLLM benefits)
echo 1024 > /proc/sys/vm/nr_hugepages
```
