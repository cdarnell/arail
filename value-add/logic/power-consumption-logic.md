# Power Consumption Logic

## Default Rate
- $0.10 per kWh (local workstation)

### Math
- Power cost = (Wattage × Duration in hours) / 1000 × $0.10
- Example: 200W × 1h = 200Wh = 0.2kWh × $0.10 = $0.02

### Prometheus Query (NVIDIA Exporter)
- `avg_over_time(nvidia_gpu_power_usage_watts[1m])`

### n8n Logic Flow
1. Pull real-time wattage from Prometheus using the above query
2. Calculate local cost per 1k tokens
3. Compare to cloud API standard ($0.03 per 1k tokens)
4. Output savings or cost difference

---

## Why This Matters
- Financial transparency for users
- Incentivizes local inference over cloud APIs
