# Scheduled Jobs for Agents

This folder is the central place for defining, tracking, and reviewing all scheduled jobs for the Minimalist AI Lab.

- **Purpose:**
  - Any job or task that should be run on a schedule (e.g., rolling updates, maintenance, periodic health checks) is defined here.
  - Jobs are considered "scheduled" if they are listed in a `*.yaml.schedule` file in this folder.
  - This makes it easy for agents (and humans) to discover, audit, and update scheduled tasks.

## How to Use

1. **Add a New Scheduled Job:**
   - Create a new file with the `.yaml.schedule` extension (e.g., `rolling-update.yaml.schedule`).
   - Define the job, schedule, and any agent logic or triggers needed.

2. **Visibility:**
   - All jobs in this folder are considered active schedules.
   - Agents can scan this folder to discover what needs to be run and when.

3. **Example:**

```yaml
# rolling-update.yaml.schedule
schedule: "0 3 * * *" # Every day at 3am
job: rolling-update
component: all
notes: |
  Perform a rolling update of all core services to minimize downtime and apply new configs.
```

---

> **Tip:** Use this folder to coordinate all periodic or automated agent actions. If it's in here, it's on the schedule!