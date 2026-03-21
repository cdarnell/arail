# Setup & Installation (Helm)

## Preferred Method

Use the Helm chart in `helm/k8s-lite` for all deployments. This is the single source of truth for the Minimalist stack.

### Install
```sh
helm install minimalist ./helm/k8s-lite
```

### Upgrade
```sh
helm upgrade minimalist ./helm/k8s-lite
```

## Pre-Install Auto-Discovery (Recommended)

Before installing the Helm chart, run the Pre-Install Probe to auto-discover host hardware and generate tuned `values.yaml` defaults. This step is recommended for first-time installs or when moving the lab to a new machine.

1. Ensure the probe dependencies are installed:

```bash
cd <repo-root>
python -m venv .venv
source .venv/bin/activate    # macOS / Linux
pip install -r scripts/preinstall/requirements.txt
```

2. Run the probe and generate recommendations:

```bash
python scripts/preinstall/hardware_probe.py --output helm/k8s-lite/values.generated.yaml
# Review helm/k8s-lite/values.generated.yaml and then apply if desired
python scripts/preinstall/hardware_probe.py --apply
```

3. Now install the Helm chart (with your verified values):

```bash
helm install minimalist ./helm/k8s-lite -f helm/k8s-lite/values.generated.yaml
```

Note: The repo includes `k8s-lite/preinstall-minimalist.sh` which will run the probe automatically if Python is available. The probe is conservative and intended as a helpful default—please review generated values before applying.

## Legacy/Manual

The `k8s-lite/` folder is deprecated and only for reference or manual/legacy use.
