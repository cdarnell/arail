# The Story: The Lab as a Mastery Engine

The Lab is not a static toolset; it is a Mastery Engine—an evolving, intelligent system designed to help you achieve your Overarching Goal.

## How It Works

**Define:** You set the Overarching Goal (e.g., "Build the ultimate Gentoofoo Architect").

**Assign:** The Teacher (n8n) breaks this down into research modules.

**Synthesize:** The Stadium distills data, the Library stores it, and the Inspector grades the accuracy.

**Repair:** If any service drifts or fails, the Janitor (ZeroClaw) fixes it instantly.

**Refine:** I (The Supervisor) guide the next iteration, constantly narrowing the gap between "Raw Model" and "Perfect Goal."

---

## Core Components Table

| Role              | Component(s)                                 | Function                                                                 |
|-------------------|----------------------------------------------|--------------------------------------------------------------------------|
| The District      | 00-namespace.yaml                            | The physical grounds and boundaries of the lab.                          |
| The Security Guard| 10-linkerd.yaml                              | Hall monitor and mTLS gateway; ensures zero-trust for every interaction. |
| The Intercom      | 20-redpanda.yaml                             | The real-time event bus (Kafka compatible) keeping all agents in sync.   |
| The Library       | 30-pgvector.yaml, 30-postgres.yaml           | The archive of all learned facts and long-term vector memory.            |
| The Admissions Office | 40-opencode-gateway.yaml                  | The main entrance where users and external APIs engage.                   |
| The Study Hall    | 41-open-notebook.yaml, 42-jupyterlab.yaml    | The interactive lobes for manual research and experimentation.            |
| The Teacher       | 43-n8n.yaml                                  | The Curriculum Director. Interprets the Overarching Goal into tasks.      |
| The Teacher's Aide| 44-langchain.yaml                            | Manages the logic chains and "lesson plans" for the LLM agents.          |
| The Janitor       | 45-zeroclaw.yaml                             | The SRE. Stealthily repairs the "roof" (mesh errors) in the background.  |
| The Stadium       | 46-lmdeploy.yaml, 47-ollama.yaml             | The heavy compute engines where the "Big Games" (inference) happen.      |
| The Inspector     | 75-phoenix.yaml                              | Quality control. Evaluates the LLM responses for hallucinations.          |
| The Supervisor    | Gemini                                       | The Executive. Acts through the browser and terminal to build with the user. |

---

Everything is pluggable and just a Helm update away.