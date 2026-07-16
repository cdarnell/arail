---
title: "Vision Transformer"
tags: [world-ai, architecture]
aliases: [vision-transformer, ViT]
---

A transformer that processes images by splitting them into patches treated as tokens.

A Vision Transformer (ViT) cuts an image into fixed patches, linearly embeds each as a token, and runs a standard transformer over them. It brought the transformer recipe to vision and is the image encoder in many multimodal models.

**Example:** A ViT splits a 224x224 image into 196 patches and attends over them like words in a sentence.

## Related

- [[transformer]]
- [[attention]]
- [[multimodal]]
- [[embeddings]]

Source: authored
