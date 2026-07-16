---
title: "Overfitting"
tags: [world-ai, training]
aliases: [overfitting]
---

When a model memorizes training-set quirks and fails to generalize to new data.

Overfitting is the gap between strong training performance and weak performance on unseen data: the model has fit noise and idiosyncrasies rather than the underlying pattern. It is diagnosed by a diverging train-vs-validation curve and countered with more data, regularization, or a smaller model.

**Example:** Validation loss starts rising while training loss keeps falling — the classic overfitting signature; stop or regularize.

## Related

- [[regularization]]
- [[dropout]]
- [[weight-decay]]
- [[eval]]
- [[benchmark]]

Source: authored
