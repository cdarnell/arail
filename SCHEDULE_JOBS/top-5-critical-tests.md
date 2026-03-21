# Top 5 Critical Scheduled Test Cases for Kubernetes Environments

These are best-practice jobs to schedule for a healthy, reliable cluster. Each should be defined as a `.yaml.schedule` file in this folder.

1. **Cluster Health Check**
   - Ensure all nodes, pods, and services are healthy and Ready. Alert on failures or restart loops.
2. **Pod Resource Usage Audit**
   - Check for pods exceeding CPU/memory limits or with OOMKilled events. Recommend right-sizing.
3. **Persistent Volume Health**
   - Verify all PVCs are Bound and accessible. Alert if any are Lost or Pending.
4. **Image Vulnerability Scan**
   - Scan all running images for known CVEs. Alert and optionally quarantine vulnerable pods.
5. **Backup & Restore Test**
   - Regularly back up critical data (e.g., Postgres, vector DB) and test restore to a staging namespace.

---

> **Pause Jobs**: A "Pause Jobs" break glass button should be available on the dashboard (next to Notebooks and Terminal) to temporarily halt all scheduled jobs. This allows users to focus on LLM processing or benchmarking without maintenance interruptions.
