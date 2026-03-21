Hardware Probe & Auto-Tuner

This small utility detects host hardware (CPU, RAM, GPUs) across Linux, macOS, and Windows and generates recommended resource values for the Helm `values.yaml` used by the Minimalist lab.

Quick start:

1. Create a Python virtualenv and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate    # macOS / Linux
. .venv\Scripts\activate  # Windows (PowerShell: .\.venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

2. Run the probe and write recommendations to `helm/k8s-lite/values.generated.yaml`:

```bash
python hardware_probe.py --output helm/k8s-lite/values.generated.yaml
```

3. Review the generated file and, when satisfied, apply it to your live `values.yaml`:

```bash
python hardware_probe.py --apply
```

Notes:
- The script is conservative and intended for non-expert users—values are suggestions and can be safely edited.
- The script supports NVIDIA GPUs via `nvidia-smi`. On macOS it queries `system_profiler` for display devices.
- If `--apply` is used, a backup of the original `values.yaml` will be created.

Feedback and improvements welcome—this is meant to be a friendly on-ramp for sharing the lab with friends and family.
