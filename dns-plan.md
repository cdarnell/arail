# DNS Plan for Air-Gapped Local Operation

## Local DNS with /etc/hosts
- **TODO:** Document how to edit `/etc/hosts` in WSL Ubuntu for local DNS entries.
- Example:
  ```
  127.0.0.1 lmdeploy.local
  127.0.0.1 metrics.local
  127.0.0.1 opencode.local
  127.0.0.1 prometheus.local
  ```

## Traefik Routing for Local Services
- **TODO:** How Traefik will route local services (lmdeploy.local, metrics.local, etc.)

## Exposing Services Under Local Hostnames
- **TODO:** Steps to expose LMDeploy, ZeroClaw, Opencode, Prometheus under local hostnames.

## Tailscale MagicDNS
- **TODO:** How MagicDNS fits in, if used for fallback or mesh.

## Keeping Everything Offline
- **TODO:** Tips for ensuring all services are self-contained and offline.

---

## Example Commands
- **Test DNS resolution:**
  ```bash
  ping lmdeploy.local
  ```
- **Check /etc/hosts:**
  ```bash
  cat /etc/hosts
  ```

*Replace TODOs with actual steps as you implement each part.*
