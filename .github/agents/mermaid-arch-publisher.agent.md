---
name: mermaid-arch-publisher
applyTo:
  - observability/architecture.mmd
  - observability/README.md
  - '**/architecture.mmd'
description: |
  Subagent that generates a fresh Mermaid architecture diagram daily from the current Minimalist stack configuration and publishes it to a designated location (e.g., docs, dashboard, or web endpoint). Ensures architectural visibility as the system evolves. Can be config-driven to reflect changes in services, namespaces, or mesh topology.
workflow:
  - step: Parse current stack configuration and inventory (OBSERVABILITY_INVENTORY.md, manifests, etc.)
  - step: Generate updated Mermaid diagram (architecture.mmd)
  - step: Commit and publish the diagram to the docs or dashboard location
  - step: Optionally trigger a notification or dashboard update
schedule: daily
triggers:
  - config change in observability/ or inventory files
  - manual invocation
restrictions:
  - Only edits architecture.mmd and related docs
  - No destructive actions
---

# Mermaid Architecture Publisher Agent

This agent ensures the Minimalist stack's architecture diagram is always up to date and visible. It runs daily (or on config change), parses the current state, and publishes a fresh Mermaid diagram for team visibility.

## Usage
- Runs automatically each day
- Can be triggered manually after major changes
- Publishes to docs or dashboard for easy access

## Customization
- Update the workflow to add new sources or destinations
- Integrate with CI/CD or dashboard as needed
