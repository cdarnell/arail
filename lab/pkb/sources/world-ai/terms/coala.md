---
title: "CoALA"
tags: [world-ai, architecture]
aliases: [coala, Cognitive Architectures for Language Agents]
---

A framework (Princeton, 2023) organizing language agents into memory modules, an action space, and a decision-making loop.

CoALA — Cognitive Architectures for Language Agents — is a conceptual framework that structures an LLM-based agent like a classical cognitive architecture. It separates the agent's memory into modules (working, episodic, semantic, procedural), defines an action space split into internal actions (reasoning, retrieval, learning) and external actions (grounding in the world via tools/environments), and a decision-making procedure that loops: propose, evaluate, and select the next action. It gives a shared vocabulary for comparing agent designs.

**Example:** Mapping an agent to CoALA: its vector store is semantic memory, its run log is episodic memory, its prompt scratchpad is working memory, and 'call a tool' is an external grounding action.

## Related

- [[agent]]
- [[agentic]]
- [[working-memory]]
- [[episodic-memory]]
- [[semantic-memory]]
- [[procedural-memory]]
- [[react]]

Source: Sumers, Yao, Narasimhan & Griffiths, 'Cognitive Architectures for Language Agents' (2023), arXiv:2309.02427
