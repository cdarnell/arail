---
title: "Top-k Sampling"
tags: [world-ai, inference]
aliases: [top-k]
---

Restrict sampling to the k most probable next tokens, then renormalize and draw from those.

Top-k sampling truncates the distribution to the k highest-probability tokens before sampling, cutting off the long tail of unlikely (often nonsensical) options. It trades a little diversity for coherence; the right k depends on how peaked the distribution is at each step.

**Example:** With k=40, the model never blurts an absurd 50,000th-ranked token, but still varies among the plausible ones.

## Related

- [[top-p]]
- [[sampling]]
- [[temperature]]
- [[greedy-decoding]]

Source: authored
