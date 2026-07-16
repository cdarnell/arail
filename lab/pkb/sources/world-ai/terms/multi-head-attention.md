---
title: "Multi-Head Attention"
tags: [world-ai, architecture]
aliases: [multi-head-attention, MHA]
---

Run several attention operations in parallel, each in its own subspace, then concatenate.

Multi-head attention splits the model dimension into several 'heads', each with its own learned query/key/value projections, runs attention independently per head, and concatenates the results. Different heads specialize — some track syntax, some long-range coreference — letting one layer attend to multiple kinds of relationship at once.

**Example:** One head links verbs to their subjects while another tracks quotation boundaries, in the same layer.

## Related

- [[attention]]
- [[transformer]]
- [[grouped-query-attention]]
- [[tri-attention]]

Source: authored
