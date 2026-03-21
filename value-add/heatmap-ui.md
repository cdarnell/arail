# Heatmap UI — Design & Snippets

This file describes the heatmap UI and provides a minimal React snippet for embedding a service heatmap on the Lungs frontpage.

Design:

- Heatmap grid: each cell represents a deployed service or pod group.
- Color: based on recent service_time_ms (warmer = slower).
- Hover: metrics snapshot (p50/p95 latency, tokens used, inference_time_ms, rps) + traces link.
- Kill button: small red `Kill -9` icon appears on hover; clicking opens confirmation modal and requires RBAC approval. Actions are logged to Janitor.

React snippet (concept):

```tsx
// HeatmapTile component: show metrics and hover controls
function HeatmapTile({service, metrics, onKill}){
  const color = heatColor(metrics.service_time_ms);
  return (
    <div className="tile" style={{background: color}} title={service}>
      <div className="tile-label">{service}</div>
      <div className="tile-metrics">{metrics.p50}ms / {metrics.p95}ms</div>
      <div className="tile-actions">
        <button className="trace-btn" onClick={()=>openTraces(service)}>Traces</button>
        <button className="kill-btn" onClick={()=>confirmKill(service, onKill)}>Kill -9</button>
      </div>
    </div>
  )
}

// Parent: fetch metrics and render grid
function HeatmapGrid(){
  const [cells, setCells] = React.useState([]);
  useEffect(()=>{
    fetch('/api/observability/heatmap')
      .then(r=>r.json()).then(setCells);
  },[]);
  return (
    <div className="heatmap-grid">
      {cells.map(c=> <HeatmapTile key={c.service} service={c.service} metrics={c.metrics} onKill={doKill} />)}
    </div>
  )
}
```

Notes:

- Implement `/api/observability/heatmap` to aggregate Prometheus and tracing metadata (Tempo/Loki) and produce the required metrics per service.
- Kill action should call a guarded backend endpoint that checks the operator's RBAC role and records the action to an audit log before issuing `kubectl delete pod --force --grace-period=0` (or equivalent API call).
```
