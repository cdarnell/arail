---
title: "Tree of Thoughts"
tags: [world-ai, architecture]
aliases: [tree-of-thoughts, ToT]
---

Explore multiple reasoning branches as a search tree, evaluating and backtracking, instead of one chain.

Tree of Thoughts generalizes chain-of-thought into a search: the model generates several candidate next steps, scores them, and explores promising branches with backtracking. It trades more compute for better performance on problems needing exploration or planning.

**Example:** On a puzzle, the model expands several partial solutions, prunes dead ends, and pursues the best branch.

## Related

- [[chain-of-thought]]
- [[self-consistency]]
- [[reasoning]]
- [[planning]]
- [[react]]

Source: authored
