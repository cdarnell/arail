"""Curated AI / model-building glossary — the default dictionary content.

This ships as built-in data so the Dictionary is instantly full and useful
with no model call. Each entry has a one-line ``short_def`` (shown on the
card) and a 2-3 sentence ``detail`` (shown on expand). Buddy can enrich any
term further on demand via the /api/dictionary/expand endpoint, but the lab
owner never sees an empty box waiting on the model.

Keep entries beginner-friendly and concrete. ``related`` links use display
terms; the renderer matches them loosely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

# (term, category, short_def, detail, related)
_GLOSSARY: List[tuple] = [
    # ── Foundations ──────────────────────────────────────────────────────
    ("Neural Network", "Foundations",
     "Layers of interconnected 'neurons' that learn patterns from data.",
     "A neural network maps inputs to outputs through layers of weighted connections. "
     "During training it adjusts those weights so its predictions get closer to the truth. "
     "Deep networks stack many layers, letting later layers build on features found by earlier ones.",
     ["Parameter", "Backpropagation", "Tensor"]),
    ("Parameter", "Foundations",
     "The learned numbers inside a model that encode what it knows.",
     "Parameters (also called weights) are the values a model tunes during training. "
     "A model's size is usually quoted by its parameter count — '3B' means three billion. "
     "More parameters can capture more, but cost more memory and compute to run.",
     ["Neural Network", "Quantization", "Fine-Tuning"]),
    ("Tensor", "Foundations",
     "A multi-dimensional array — the basic data structure models compute on.",
     "Scalars, vectors, and matrices generalize to tensors. A model's inputs, weights, and "
     "activations all flow through the network as tensors, which is why GPUs — great at parallel "
     "array math — are the workhorses of deep learning.",
     ["Neural Network", "Embedding"]),
    ("Embedding", "Foundations",
     "A vector of numbers that represents meaning so models can compute with it.",
     "Words, sentences, or images are turned into dense vectors so that similar things sit close "
     "together in vector space. Embeddings power semantic search and retrieval — comparing vectors "
     "finds related content even without exact word matches.",
     ["Token", "RAG", "Tensor"]),
    ("Token", "Foundations",
     "The chunk of text a model reads and writes — often a word piece, not a whole word.",
     "Models don't see characters or words directly; text is split into tokens by a tokenizer. "
     "'tokenization' might become 'token' + 'ization'. Token counts drive cost, speed, and the "
     "context-window limit.",
     ["Tokenization", "Context Window", "Embedding"]),
    ("Tokenization", "Foundations",
     "Splitting text into tokens the model can process.",
     "A tokenizer converts raw text into a sequence of integer token IDs and back again. Subword "
     "tokenizers (like BPE) balance vocabulary size against sequence length, handling rare words by "
     "breaking them into familiar pieces.",
     ["Token"]),

    # ── Architecture ─────────────────────────────────────────────────────
    ("Transformer", "Architecture",
     "The neural-network architecture behind modern large language models.",
     "Introduced in 2017's 'Attention Is All You Need', the transformer processes a whole sequence "
     "in parallel using attention instead of step-by-step recurrence. It scales well, which is why "
     "nearly every large language model is a transformer.",
     ["Attention", "Encoder / Decoder", "Context Window"]),
    ("Attention", "Architecture",
     "A mechanism that lets a model weigh which other tokens matter for each token.",
     "Self-attention compares every token with every other token and produces a weighted blend, so "
     "the model can 'focus' on relevant context — like linking a pronoun to the noun it refers to. "
     "It's the core idea that makes transformers powerful.",
     ["Transformer", "Multi-Head Attention", "KV Cache"]),
    ("Multi-Head Attention", "Architecture",
     "Running several attention operations in parallel to capture different relationships.",
     "Each 'head' learns to focus on a different kind of pattern — syntax, position, topic — and "
     "their results are combined. Multiple heads give the model several perspectives on the same "
     "sequence at once.",
     ["Attention", "Transformer"]),
    ("Context Window", "Architecture",
     "The maximum number of tokens a model can consider at once.",
     "Everything the model 'sees' — your prompt plus its reply — must fit in the context window. "
     "Larger windows allow longer documents and conversations, but cost more memory and compute, "
     "partly because of the KV cache.",
     ["Token", "KV Cache", "Attention"]),
    ("Encoder / Decoder", "Architecture",
     "Two transformer roles: one reads input, one generates output.",
     "Encoders build a rich representation of the input (good for understanding tasks); decoders "
     "generate tokens one at a time (good for text generation). Chat LLMs are typically "
     "decoder-only, predicting the next token over and over.",
     ["Transformer", "Inference"]),
    ("Mixture of Experts", "Architecture",
     "A model that routes each token to a few specialized sub-networks.",
     "Instead of using all parameters for every token, a Mixture-of-Experts (MoE) model activates "
     "only a handful of 'expert' subnetworks per token. This gives a large total parameter count "
     "while keeping the compute per token low.",
     ["Parameter", "Inference"]),

    # ── Training ─────────────────────────────────────────────────────────
    ("Forward Pass", "Training",
     "Running input through the model to get a prediction.",
     "In the forward pass, data flows from input to output, layer by layer, producing the model's "
     "prediction. Comparing that prediction to the truth gives the loss, which drives learning.",
     ["Backpropagation", "Loss Function"]),
    ("Backpropagation", "Training",
     "The algorithm that figures out how to adjust each weight to reduce error.",
     "After a forward pass, backpropagation works backward through the network using the chain rule "
     "to compute how much each weight contributed to the error. Those gradients tell the optimizer "
     "which direction to nudge every parameter.",
     ["Gradient Descent", "Loss Function", "Optimizer"]),
    ("Gradient Descent", "Training",
     "Iteratively nudging weights downhill to minimize the loss.",
     "Picture the loss as a landscape; gradient descent takes small steps in the steepest downhill "
     "direction. The step size is the learning rate. Variants like SGD and Adam make this faster "
     "and more stable.",
     ["Learning Rate", "Optimizer", "Backpropagation"]),
    ("Loss Function", "Training",
     "A score for how wrong the model's prediction is.",
     "Training minimizes the loss. For language models it's usually cross-entropy — how surprised "
     "the model was by the correct next token. Lower loss means better predictions on the training "
     "data.",
     ["Perplexity", "Backpropagation"]),
    ("Learning Rate", "Training",
     "How big a step the optimizer takes on each update.",
     "Too high and training overshoots or diverges; too low and it crawls. The learning rate is one "
     "of the most important knobs to tune, often paired with a schedule that lowers it over time.",
     ["Gradient Descent", "Optimizer"]),
    ("Epoch / Batch / Step", "Training",
     "Units of training progress.",
     "A batch is a group of examples processed together; a step is one weight update on one batch; "
     "an epoch is one full pass over the dataset. Bigger batches are more stable but use more "
     "memory.",
     ["Dataset", "Gradient Descent"]),
    ("Optimizer", "Training",
     "The algorithm that turns gradients into actual weight updates (e.g. Adam).",
     "Optimizers decide how to apply gradients. Adam, the most common, adapts the step size per "
     "parameter using running averages of past gradients, making training faster and more robust "
     "than plain gradient descent.",
     ["Gradient Descent", "Learning Rate"]),
    ("Overfitting", "Training",
     "When a model memorizes training data and fails to generalize.",
     "An overfit model scores well on data it has seen but poorly on new data. It's the central "
     "tension in machine learning; more data, regularization, and validation checks fight it.",
     ["Regularization", "Train/Val/Test Split"]),
    ("Regularization", "Training",
     "Techniques that discourage a model from overfitting.",
     "Methods like dropout, weight decay, and early stopping keep a model from leaning too hard on "
     "quirks of the training set, trading a little training accuracy for better real-world "
     "generalization.",
     ["Overfitting"]),
    ("Pretraining", "Training",
     "The first, large-scale training phase on broad data.",
     "A base model is pretrained on enormous amounts of text to learn general language and world "
     "patterns. This is the expensive phase; later fine-tuning specializes the model cheaply on top "
     "of it.",
     ["Fine-Tuning", "Transfer Learning"]),

    # ── Fine-Tuning ──────────────────────────────────────────────────────
    ("Fine-Tuning", "Fine-Tuning",
     "Further training a pretrained model on a smaller, focused dataset.",
     "Fine-tuning adapts a general base model to a specific task, domain, or style using far less "
     "data and compute than training from scratch. It's how most specialized models are made.",
     ["Pretraining", "LoRA", "Transfer Learning"]),
    ("Transfer Learning", "Fine-Tuning",
     "Reusing knowledge from one task to bootstrap another.",
     "Instead of starting from random weights, you start from a model that already learned useful "
     "representations and adapt it. It's why a model pretrained on the open web can be fine-tuned "
     "for medicine or law quickly.",
     ["Fine-Tuning", "Pretraining"]),
    ("LoRA", "Fine-Tuning",
     "Low-Rank Adaptation — efficient fine-tuning that trains tiny add-on matrices.",
     "Rather than updating all of a model's weights, LoRA freezes them and learns small low-rank "
     "matrices alongside. This cuts memory and storage dramatically, so you can fine-tune big "
     "models on modest hardware and swap adapters in and out.",
     ["Fine-Tuning", "PEFT", "Quantization"]),
    ("PEFT", "Fine-Tuning",
     "Parameter-Efficient Fine-Tuning — adapt a model by training only a small slice of it.",
     "PEFT is the family of methods (LoRA, adapters, prefix tuning) that update a tiny fraction of "
     "parameters instead of the whole model — making fine-tuning cheap, fast, and modular.",
     ["LoRA", "Fine-Tuning"]),
    ("RLHF", "Fine-Tuning",
     "Reinforcement Learning from Human Feedback — aligning models to human preference.",
     "Humans rank model outputs; those rankings train a reward model; the LLM is then optimized to "
     "produce higher-reward responses. RLHF is a big reason chat models feel helpful and follow "
     "instructions.",
     ["Instruction Tuning", "Fine-Tuning"]),
    ("Instruction Tuning", "Fine-Tuning",
     "Fine-tuning a model to follow natural-language instructions.",
     "By training on many (instruction, ideal-response) pairs, a base model learns to do what it's "
     "told rather than just continue text. It's the step that turns a raw predictor into an "
     "assistant.",
     ["Fine-Tuning", "RLHF", "Prompt"]),

    # ── Prompting & Retrieval ────────────────────────────────────────────
    ("Prompt", "Prompting",
     "The input text you give a model to steer its output.",
     "The prompt is your interface to the model. Clear instructions, examples, and context in the "
     "prompt strongly shape the result — the craft of writing them is called prompt engineering.",
     ["Few-Shot / Zero-Shot", "Context Window", "Instruction Tuning"]),
    ("Few-Shot / Zero-Shot", "Prompting",
     "Giving a model a few examples (or none) in the prompt.",
     "Zero-shot asks the model to do a task with no examples; few-shot includes a handful to "
     "demonstrate the pattern. Few-shot often boosts accuracy without any retraining — the model "
     "learns from context.",
     ["Prompt", "Instruction Tuning"]),
    ("RAG", "Prompting",
     "Retrieval-Augmented Generation — letting a model pull in external documents before answering.",
     "RAG retrieves relevant text (often via embeddings) and feeds it into the prompt so the model "
     "can answer from up-to-date or private knowledge it wasn't trained on — reducing hallucination "
     "and avoiding retraining.",
     ["Embedding", "Hallucination", "Context Window"]),

    # ── Data ─────────────────────────────────────────────────────────────
    ("Dataset", "Data",
     "The collection of examples a model learns from.",
     "Quality and diversity of the dataset largely determine model quality — 'garbage in, garbage "
     "out'. Datasets are usually split into training, validation, and test portions.",
     ["Train/Val/Test Split", "Data Augmentation"]),
    ("Train/Val/Test Split", "Data",
     "Partitioning data to train, tune, and honestly evaluate a model.",
     "The model learns on the training set, hyperparameters are chosen using the validation set, "
     "and final performance is measured once on the untouched test set — so the score reflects real "
     "generalization.",
     ["Overfitting", "Dataset", "Benchmark"]),
    ("Data Augmentation", "Data",
     "Expanding a dataset by creating modified copies of examples.",
     "Flipping images, paraphrasing text, or adding noise gives a model more varied examples to "
     "learn from, improving robustness and reducing overfitting without collecting new data.",
     ["Dataset", "Regularization"]),

    # ── Inference ────────────────────────────────────────────────────────
    ("Inference", "Inference",
     "Running a trained model to get outputs — what happens when you use it.",
     "Inference is the 'serving' phase, distinct from training. The metrics that matter shift to "
     "latency (time to respond) and throughput (requests per second), and to fitting the model in "
     "available memory.",
     ["Quantization", "KV Cache", "Temperature"]),
    ("Quantization", "Inference",
     "Shrinking a model by storing weights at lower numeric precision.",
     "Converting weights from 16-bit to 8- or 4-bit cuts memory and speeds up inference, often with "
     "little quality loss. It's what lets large models run on laptops and consumer GPUs.",
     ["Parameter", "Inference", "Distillation"]),
    ("Temperature", "Inference",
     "A knob that controls how random a model's output is.",
     "Low temperature makes the model pick the most likely tokens (focused, repetitive); high "
     "temperature flattens the odds (creative, riskier). It's the simplest dial for tuning output "
     "style.",
     ["Top-p / Top-k", "Inference"]),
    ("Top-p / Top-k", "Inference",
     "Strategies for choosing the next token from the probability distribution.",
     "Top-k limits choices to the k most likely tokens; top-p (nucleus) keeps the smallest set "
     "whose probabilities sum to p. Both trade coherence against diversity, usually paired with "
     "temperature.",
     ["Temperature", "Token"]),
    ("KV Cache", "Inference",
     "Stored attention values that make generating each new token fast.",
     "During generation the model caches the key/value tensors of past tokens so it doesn't "
     "recompute them every step. The KV cache speeds up inference but grows with context length, "
     "eating memory.",
     ["Attention", "Context Window", "Inference"]),
    ("Distillation", "Inference",
     "Training a small 'student' model to imitate a large 'teacher'.",
     "Knowledge distillation transfers the behavior of a big, capable model into a smaller, cheaper "
     "one by training the student on the teacher's outputs — keeping much of the quality at a "
     "fraction of the cost.",
     ["Quantization", "Fine-Tuning"]),

    # ── Evaluation ───────────────────────────────────────────────────────
    ("Benchmark", "Evaluation",
     "A standard test used to compare models.",
     "Benchmarks (like MMLU or HumanEval) give models the same tasks so results are comparable. "
     "They're useful but imperfect — models can be tuned to the test, so real-world evaluation "
     "still matters.",
     ["Perplexity", "Train/Val/Test Split"]),
    ("Perplexity", "Evaluation",
     "A measure of how well a model predicts text — lower is better.",
     "Perplexity is roughly how 'surprised' the model is by the next token, on average. It's a "
     "quick intrinsic metric for language models, though it doesn't fully capture usefulness.",
     ["Loss Function", "Benchmark"]),
    ("Hallucination", "Evaluation",
     "When a model states something false with confidence.",
     "Because models generate plausible-sounding text rather than looking up facts, they sometimes "
     "invent details. Grounding techniques like RAG and careful prompting reduce — but don't "
     "eliminate — hallucination.",
     ["RAG", "Benchmark"]),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_entries() -> List[Dict[str, Any]]:
    """Return the curated glossary as normalized term dicts.

    Imported lazily by DictionaryStore so it costs nothing until the default
    theme is first opened. Each call returns fresh dicts (no shared mutation)."""
    from arail.dictionary import norm_key

    out: List[Dict[str, Any]] = []
    ts = _now()
    for term, category, short_def, detail, related in _GLOSSARY:
        out.append({
            "term": term,
            "short_def": short_def,
            "detail": detail,
            "detail_source": "curated",
            "category": category,
            "examples": [],
            "origin": "",
            "related": list(related),
            "key": norm_key(term),
            "created_at": ts,
            "builtin": True,
        })
    return out
