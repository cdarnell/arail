# Autoresearch Project: Overarching Goals & Experiments

This document outlines the core research experiments and overarching goals for integrating the [karpathy/autoresearch](https://github.com/karpathy/autoresearch) project into the Minimalist AI Lab. These experiments are designed to help researchers iteratively refine, compress, and personalize LLMs for targeted use cases, efficiency, and safety.

## Overarching Goals
- Enable researchers to define and pursue high-level LLM optimization and distillation objectives.
- Provide a reproducible, GPU-friendly environment for running and iterating on autoresearch experiments.
- Integrate results and workflows into the broader AI Lab for collaborative, agentic research.

## Core Experiments

### 1. Tokenizer Pruning Experiment
- **Remove:**
  - Languages you don’t need
  - Scripts you’ll never use
  - Emoji if irrelevant
  - Domain‑specific tokens you don’t care about
- **Measure:**
  - Embedding matrix shrink
  - Perplexity impact
  - Downstream accuracy

### 2. Knowledge Retention Distillation
- **Teacher:** Full model
- **Student:** Smaller model
- **Objective:**
  - Keep reasoning
  - Keep your preferred domains
  - Drop everything else

### 3. Domain‑Focused Distillation
- **Train the student only on:**
  - Your documents
  - Your workflows
  - Your coding style
  - Your preferred tools
  - Your product ecosystem
- **Goal:** Create a personalized expert model

### 4. Language Removal Experiment
- **Remove:**
  - Chinese, Arabic, French, Spanish, Cyrillic, etc.
- **Evaluate:**
  - English performance
  - Reasoning
  - Hallucination rate

### 5. Structured Knowledge Compression
- **Use:**
  - QLoRA
  - SFT
  - RAG‑guided distillation
  - Synthetic data generation
- **Goal:** Compress your knowledge into fewer parameters

### 6. Reasoning‑Only Distillation
- **Distill only:**
  - Chain‑of‑thought
  - Planning
  - Tool‑use
  - Agentic reasoning
- **Drop:**
  - Trivia
  - World knowledge
  - Irrelevant domains

### 7. Safety‑Preserving Pruning
- **Prune aggressively but ensure:**
  - No harmful outputs
  - No broken reasoning
  - No degraded tool‑use

### 8. Efficiency‑Driven Architecture Search
- **Try:**
  - Smaller hidden sizes
  - Fewer layers
  - Grouped-query attention
  - Sliding window attention
  - Mixture‑of‑experts
- **Measure:**
  - Throughput
  - Memory footprint
  - Latency

### 9. Dataset Curation Experiment
- **Compare:**
  - Curated dataset
  - Synthetic dataset
  - Filtered dataset
  - Domain‑specific dataset
- **Measure:**
  - Knowledge retention
  - Hallucination reduction

### 10. Multi‑Stage Distillation Pipeline
- **Teacher → Mid‑Student → Final‑Student**
- **Why:**
  - Smoother compression
  - Better retention
  - Fewer catastrophic losses

---

*Update this document as new experiments or research goals are added. Integrate findings and workflows into the AI Lab for collaborative progress.*
