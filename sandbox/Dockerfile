# BEE ML sandbox — pre-built Python env where code_run/sandbox_run execute.
#
# Build (CPU baseline):
#   docker build -t bee-sandbox:latest .
#
# GPU build (RTX 3050): create Dockerfile.gpu from this file by changing the
# base to nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 and installing the
# cu124 torch wheel — see GPU section at bottom.
#
# The BEE workspace is mounted at /workspace at runtime (handled by the tool).

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# uv = fast, reproducible env management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU baseline torch (GPU variant: rebuild with --index-url .../cu124, see bottom)
RUN uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Rest of the ML stack
RUN uv pip install \
    numpy pandas polars pyarrow dask \
    scikit-learn lightgbm xgboost imbalanced-learn shap \
    pytorch-lightning \
    transformers datasets peft accelerate onnxruntime \
    opencv-python-headless \
    matplotlib seaborn scipy sympy networkx nltk \
    mlflow \
    pytest memory-profiler \
    playwright \
    && playwright install chromium --with-deps

# HF cache inside the mounted workspace (visible on host, easy to clean)
ENV HF_HOME=/workspace/.hf

CMD ["bash"]

# ---------------------------------------------------------------------
# GPU variant (RTX 3050 8GB) — build with:
#   sed 's|python:3.11-slim|nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04|; /whl\/cpu/d' Dockerfile > Dockerfile.gpu
#   docker build -f Dockerfile.gpu -t bee-sandbox:gpu .
# and install torch with the cu124 index:
#   RUN uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
# Verify:  docker run --rm --gpus all bee-sandbox:gpu python -c "import torch; print(torch.cuda.is_available())"
# ---------------------------------------------------------------------
