# Power-Aware Cost Simulator Logic

## Overview
This simulator quantifies the cost of running local LLM inference versus using cloud APIs, based on power consumption and API pricing.

- **Default Power Cost:** $0.10/kWh (local)
- **Cloud API Cost:** Variable, based on provider pricing

### Workflow
1. Measure inference duration and wattage
2. Calculate local power cost: 
   $$\text{Cost} = \frac{\text{Wattage} \times \text{Duration (hours)}}{1000} \times \$0.10$$
3. Compare to API cost per token/request
4. Output savings or cost difference

### Example Calculation
- Local GPU: 200W, 1 hour inference
- Local cost: $0.10/kWh × (200W × 1h / 1000) = $0.02
- Cloud API: $0.01 per 1,000 tokens

### Agent Roles
- **opencode.ai (Teacher/Orchestrator):** Explains calculations, optimization tips, and workflow logic.
- **zeroclaw (Janitor/SRE):** Monitors infrastructure, triggers cost-saving actions, and auto-remediation.

---

## Persona Mapping
- **opencode.ai:** Teacher/Orchestrator
- **zeroclaw:** Janitor/SRE (Infrastructure)

---

## Next Steps
- Add new goals and workflows as Markdown files in this directory.
- Document agent instructions for each value-add goal.
