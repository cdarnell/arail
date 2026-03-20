# Defining Value-Add Goals and Deterministic Workflows

## Purpose
The `value-add` directory is for user-defined goals that drive deterministic workflows, enabling opencode agents and the "AI Teacher" to assist, explain, and automate value creation.

---

## How to Define a Value-Add Goal
1. **Describe the Goal Clearly:**
   - What outcome do you want? (e.g., "Reduce LLM inference cost below API pricing.")
   - Why is this valuable? (e.g., "To optimize infrastructure spend and increase transparency.")
2. **Specify Inputs and Constraints:**
   - What data, metrics, or context is required?
   - Are there standards, thresholds, or best practices to follow?
3. **Trigger a Deterministic Workflow:**
   - Each goal should kick off a workflow (manual or automated) that:
     - Gathers required data
     - Runs logic or analysis
     - Produces actionable outputs (reports, alerts, dashboards, etc.)
4. **Instruction Sets for Opencode Agents:**
   - For each goal, define what the agents should do:
     - What to automate
     - What to explain ("AI Teacher" role)
     - What to document/share

---

## Example: LLM Power Consumption vs API Cost
- **Goal:** Quantify and compare the cost of local LLM inference to API usage.
- **Workflow:**
  1. Collect inference duration, wattage, and token count
  2. Calculate power cost and compare to API cost
  3. Output result and explanation
- **AI Teacher:**
  - Explains each calculation step
  - Shares optimization tips (e.g., "Try batch inference to reduce cost per token.")
  - Documents findings for future reference

---

## Why This Approach?
- Ensures every value-add is transparent, reproducible, and teachable
- Empowers users to define, measure, and improve what matters most
- Makes agent assistance explainable and actionable

---

## Next Steps
- Add new goals as Markdown files in this directory
- For each, define the workflow and agent instructions
- The "AI Teacher" will always:
  - Share how things are done
  - Suggest what could be done
  - Explain why things are done this way
