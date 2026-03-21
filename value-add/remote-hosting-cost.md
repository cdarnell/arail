# Remote Hosting Cost Simulation

Purpose: provide a simple, configurable estimator for the likely cost of using a remote hosted model (non-premium/small-host providers) so the dashboard can show a combined local+remote spend.

Modeling approach (parametric):

- `cost_per_token_usd` — cost per generated token (USD). Example non-premium ranges: 0.000001 — 0.00005 USD/token depending on model size and provider.
- `instance_hourly_usd` — if you run a hosted instance (e.g., small GPU cloud instance for a month-long endpoint), cost per hour.
- `bandwidth_per_gb_usd` — egress cost per GB.
- `avg_tokens_per_request` — average tokens generated per request.
- `requests_per_hour` — throughput.

Formulas:

- Hourly token cost = `cost_per_token_usd * avg_tokens_per_request * requests_per_hour`
- Hourly hosting cost = `instance_hourly_usd + Hourly token cost + (bandwidth_per_gb_usd * gb_per_hour)`
- Monthly cost = `Hourly hosting cost * 24 * 30` (approx)

Example presets (simulated, adjustable):

- light-hosted-model:
  - `cost_per_token_usd`: 0.000005
  - `instance_hourly_usd`: 0.10
  - `bandwidth_per_gb_usd`: 0.08

- medium-hosted-model:
  - `cost_per_token_usd`: 0.00002
  - `instance_hourly_usd`: 0.50
  - `bandwidth_per_gb_usd`: 0.08

- heavy-hosted-model:
  - `cost_per_token_usd`: 0.00005
  - `instance_hourly_usd`: 2.00
  - `bandwidth_per_gb_usd`: 0.08

Integration into dashboard:

- Add UI card under power-cost that takes: `requests_per_hour`, `avg_tokens_per_request`, and `preset`.
- Show: `hourly_remote_cost`, `monthly_remote_cost`, and combined `local_power_cost + remote_cost`.

API endpoint (concept): `/api/observability/remote-cost` accepts JSON body with params and returns cost estimates.

UI snippet (React):

```tsx
function RemoteCost({preset}){
  const [params, setParams] = React.useState({requests_per_hour:100, avg_tokens:200});
  const [est, setEst] = React.useState(null);
  useEffect(()=>{
    fetch('/api/observability/remote-cost', {method:'POST', body: JSON.stringify({preset, ...params})})
      .then(r=>r.json()).then(setEst);
  },[preset, params]);
  if(!est) return <div>Loading...</div>;
  return (
    <div>
      <div>Hourly remote cost: ${est.hourly.toFixed(3)}</div>
      <div>Monthly remote cost: ${est.monthly.toFixed(2)}</div>
    </div>
  )
}
```

Notes:

- These are simulated estimates to help trade off local GPU power cost vs hosted inference spend. Allow operators to tune `cost_per_token_usd` and instance costs.
- Store presets in `value-add/design.yml` to make them available to agents for dry-run estimations.
