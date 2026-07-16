---
title: "Switch optimizer"
tags: [world-ai, care-actions]
aliases: [switch-optimizer]
---

Change the optimizer (e.g., SGD → Adam, Adam → AdamW) to better fit the problem.

Different optimizers make different trade-offs: SGD with momentum generalizes well but is sensitive to LR and requires careful tuning; Adam adapts per-parameter LR and handles sparse gradients but is prone to weight drift; AdamW decouples weight decay from the adaptive LR and is the standard for fine-tuning transformers. Switching can resolve convergence problems when hyperparameter tuning alone fails.

**Example:** A fine-tuning run with Adam shows weight norm growth and eventual degradation; switching to AdamW with weight_decay=0.01 stabilizes the norms and improves val loss.

## Related

- [[adam-optimizer]]
- [[adamw]]
- [[learning-rate-too-low]]
- [[loss-plateau]]

Source: AdamW: Loshchilov & Hutter arXiv:1711.05101; HF Trainer docs (optim=adamw_hf); PyTorch optimizer docs
