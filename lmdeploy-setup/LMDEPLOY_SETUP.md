# LMDeploy Setup Guide (WSL Ubuntu)

## 1. Install LMDeploy from Source

- **TODO:** Step-by-step instructions for cloning and building LMDeploy from source inside WSL Ubuntu.
- **Dependencies:**
  - CUDA (version?)
  - cuDNN
  - Python (version?)
  - Build tools: gcc, g++, make, cmake, etc.
- **Example:**
  ```bash
  # TODO: Add actual install commands
  sudo apt update && sudo apt install -y build-essential python3 python3-venv python3-pip git
  # ...
  ```

## 2. Verify GPU Visibility in WSL

- **TODO:** Document commands to check GPU access (e.g., `nvidia-smi`, `lsmod | grep nvidia`).
- **Example:**
  ```bash
  nvidia-smi
  ```

## 3. Run a Test Model

- **TODO:** Example command to run a test model with LMDeploy.
- **Example:**
  ```bash
  # TODO: Replace with actual LMDeploy test command
  ./lmdeploy run --model <model-path> --prompt "Hello, world!"
  ```

## 4. Expose LMDeploy Metrics Locally

- **TODO:** How to enable and expose metrics endpoint in LMDeploy.
- **Example:**
  ```bash
  curl http://localhost:9000/metrics
  ```

## 5. Integrate LMDeploy with Prometheus

- **TODO:** Prometheus scrape config for LMDeploy metrics endpoint.
- **Example:**
  ```yaml
  scrape_configs:
    - job_name: 'lmdeploy'
      static_configs:
        - targets: ['localhost:9000']
  ```


## 6. Route LMDeploy through Linkerd Service Mesh

- **TODO:** Steps to route LMDeploy traffic via Linkerd mesh.
- Ensure LMDeploy pod/deployment has the annotation:
  ```yaml
  metadata:
    annotations:
      linkerd.io/inject: enabled
  ```
- After deployment, verify with:
  ```sh
  linkerd viz stat deploy -n <namespace>
  linkerd viz edges deploy -n <namespace>
  ```

## 7. Temporary Fallback: LM Studio over Tailscale

- **TODO:** How to use LM Studio as a fallback LLM endpoint via Tailscale.

---

## Troubleshooting

### Common Build Failures
- **TODO:** List common errors and fixes.

### Missing CUDA Libraries
- **TODO:** How to check and fix missing CUDA dependencies.

### Python Environment Issues
- **TODO:** How to resolve Python/venv issues.

### WSL GPU Passthrough Validation
- **TODO:** Commands to validate GPU passthrough in WSL.

### Confirm LMDeploy Binaries
- **TODO:** How to check LMDeploy is installed and working.

---

## Example Commands
- **Call LMDeploy locally:**
  ```bash
  curl -X POST http://localhost:8000/generate -d '{"prompt": "Hello"}'
  ```
- **Test metrics endpoint:**
  ```bash
  curl http://localhost:9000/metrics
  ```
- **Test DNS resolution:**
  ```bash
  ping lmdeploy.local
  ```
- **Run LM Studio over Tailscale:**
  ```bash
  # TODO: Add LM Studio + Tailscale usage example
  ```

---

## Visibility Pipeline
- Prometheus scrapes LMDeploy, Opencode, Gateway
- Grafana dashboards for token usage, agent activity
- Tempo/Jaeger traces for IDE agent calls
- Logs routed to Loki

---

*Replace all TODOs with actual steps as you implement each part.*
