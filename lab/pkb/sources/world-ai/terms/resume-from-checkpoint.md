---
title: "Resume from checkpoint"
tags: [world-ai, care-actions]
aliases: [resume-from-checkpoint]
---

Roll back to a saved state before the failure and restart with corrected hyperparameters.

After a divergence or NaN, the corrupted model weights must be discarded. Save checkpoints frequently during training (e.g., every 500–1000 steps) so that the last-good checkpoint is a short rollback away. Restore the checkpoint, fix the root cause (LR, clipping, precision settings), and resume. HF Trainer handles checkpoint save and resume automatically when `save_steps` and `resume_from_checkpoint` are set.

**Example:** After a NaN at step 2100, restore the step-2000 checkpoint, reduce the GradScaler's initial loss scale from 65536 to 16384, and resume; the NaN does not recur.

## Related

- [[nan-loss]]
- [[diverging-loss]]
- [[checkpoint]]

Source: HF Trainer docs (resume_from_checkpoint, save_steps); PyTorch checkpoint docs
