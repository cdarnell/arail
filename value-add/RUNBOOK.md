Runbook: Nucleus Distillation Engine

Overarching Goal (DEFAULT):
- Distill frontier-scale models into compact, local student models that reliably achieve the DNA goal (the "DNA Focus Box"). The run loop should: prescan host capabilities → fetch DNA (goal + corpus) → launch AutoResearch experiments → capture final model artefacts and metrics → deploy validated adapters for local inference.

Webhook & Orchestration (n8n + LM Studio):
- The Teacher workflow accepts LM Studio experiment completions at `/webhook/lmstudio`.
- n8n webhook node name: `LMStudio Webhook`.
- Store final experiment payloads using `Store AutoResearch Result (pgvector)`.
- Secure callbacks with the secret stored in the env var `LM_STUDIO_WEBHOOK_SECRET` (default: `changeme` until rotated).

Operational Notes:
- Ensure `WEBHOOK_BASE_URL` is set in the n8n runtime (e.g., https://lab.example.com) so experiment callbacks include the correct `callback_url`.
- If LM Studio can't POST callbacks, use polling fallback: query the experiments API and ingest final status into `Store AutoResearch Result (pgvector)`.
- First-experiment policy: every new AutoResearch run must include `target` (DNA goal), `prescan` object, `callback_url`, and `callback_secret` in the creation payload.

Runbook Actions:
- Rotate `LM_STUDIO_WEBHOOK_SECRET` periodically and update the `LMStudio`/n8n Helm values.
- Validate webhook ingress: `curl -X POST "$WEBHOOK_BASE_URL/webhook/lmstudio" -H "X-Webhook-Token: $LM_STUDIO_WEBHOOK_SECRET" -d '{"dna":"test","result":"ok"}'`
- Monitor `auto_research_results` table for new rows and confirm `commit_sha`/`val_bpb` fields are present.

Change History:
- 2026-03-21: Added default overarching goal and LM Studio webhook integration notes.
