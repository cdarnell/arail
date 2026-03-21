# Power Monitoring — Prometheus + Dashboard

Goal: show live tally of GPU power usage and cost at $0.10 per kWh on the main dashboard.

Requirements:

- GPU power metrics (DCGM exporter or equivalent) scraped by Prometheus as `node_gpu_power_watts` or similar.
- Prometheus, Grafana (or dashboard), and a small backend endpoint to calculate accumulated cost since build/start.

Prometheus queries (examples):

- Current total GPU watts:

```
sum(node_gpu_power_watts)
```

- Rolling energy (kWh) over last hour:

```
sum_over_time(node_gpu_power_watts[1h]) / 3600
```

- Cost per hour (USD) at $0.10/kWh:

```
(sum_over_time(node_gpu_power_watts[1h]) / 3600) * 0.10
```

- Instantaneous cost per minute (approx):

```
sum(node_gpu_power_watts) * (1/60) / 1000 * 0.10
```

Accumulated cost since lab start:

- Agents should emit a `lab_start_timestamp` (or the CI build timestamp) to a metadata store.
- Backend calculates accumulated kWh by integrating power from `lab_start_timestamp` to now and multiplies by 0.10.

Backend endpoint (concept, Node.js/Express):

```js
// GET /api/observability/power?since=2026-03-21T00:00:00Z
app.get('/api/observability/power', async (req, res) => {
  const since = req.query.since || process.env.LAB_START;
  // query Prometheus for sum_over_time(node_gpu_power_watts[<range>]) across windows
  // aggregate and return: { current_watts, kwh_1h, cost_per_hour_usd, accumulated_kwh, accumulated_cost_usd }
});
```

UI snippet (add to `value-add/heatmap-ui.md` or Lungs frontpage):

```tsx
function PowerTally(){
  const [power, setPower] = React.useState(null);
  useEffect(()=>{
    fetch('/api/observability/power').then(r=>r.json()).then(setPower);
  },[]);
  if(!power) return <div>Loading power...</div>;
  return (
    <div className="power-tally">
      <div>Current GPU Watts: {power.current_watts} W</div>
      <div>1h Energy: {power.kwh_1h.toFixed(3)} kWh</div>
      <div>Cost / hour: ${power.cost_per_hour_usd.toFixed(2)}</div>
      <div>Accumulated cost since build: ${power.accumulated_cost_usd.toFixed(2)}</div>
    </div>
  )
}
```

Security & accuracy notes:

- Ensure Prometheus metrics are trustworthy; prefer DCGM exporter for GPU telemetry.
- If direct power metrics are missing, approximate using `gpu_utilization * gpu_tdp` per GPU.
- Audit the accumulated cost calculation and persist intermediate snapshots for resilience.

*** End File