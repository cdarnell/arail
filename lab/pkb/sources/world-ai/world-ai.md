# AI & Machine Learning

**World:** `ai` · **bundle_version:** 1

## Terms

| Term | Short definition | Source |
|------|-----------------|--------|
| Ablation | Removing one component to measure how much it actually contributes. | QuKaiZen AI Dictionary |
| Action Space | The set of things an agent can do — internal (reason, retrieve) and external (call tools, act in the world). | authored |
| Activation Checkpointing | Trade compute for memory by recomputing activations in the backward pass instead of storing them. | authored |
| Activation Function | The nonlinear function applied to neuron outputs, letting networks model more than straight lines. | authored |
| Adam optimizer | Adaptive moment estimation — per-parameter adaptive LR via running mean and variance of gradients. | Kingma & Ba — Adam arXiv:1412.6980; Goodfellow et al. — Deep Learning §8.5; PyTorch Adam docs |
| AdamW | The default optimizer for training transformers — Adam with decoupled weight decay. | authored |
| Adapter layers | Small bottleneck modules inserted into transformer layers — trained while base model is frozen. | Houlsby et al. — Parameter-Efficient Transfer Learning arXiv:1902.00751; HF peft docs (AdapterConfig) |
| Adapters | Small trainable modules inserted into a frozen model to add new skills without retraining it. | authored |
| Add gradient clipping | Cap gradient norms before the optimizer step to prevent destabilizing updates. | PyTorch torch.nn.utils.clip_grad_norm_ docs; HF Trainer (max_grad_norm); Goodfellow et al. — Deep Learning §10.11 |
| Add regularization | Apply dropout, weight decay, or data augmentation to reduce overfitting. | Goodfellow et al. — Deep Learning ch.7; HF Trainer docs (weight_decay); PyTorch Dropout docs |
| Adversarial Swarm | A loop of agents (interrogate, challenge, evaluate, correct) that hardens a model until it stops breaking. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| AeroLLM | QuKaiZen's inference engine that streams frontier models off disk so they run without full GPU residency. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| AeroLLM (SLM runtime) | [ROADMAP] QuKaiZen's OSS inference engine for running SLMs without full GPU residency. | QuKaiZen CLAUDE.md (AeroLLM — OSS inference engine; 7B@43 tok/s measured); QuKaiZen VISION.md |
| Agent | An LLM that takes actions — calls tools, makes decisions — toward a goal, not just chats. | QuKaiZen AI Dictionary |
| Agent Loop | The repeating perceive-decide-act cycle that drives an autonomous agent. | authored |
| Agentic | Software built around autonomous, tool-using model agents. | QuKaiZen AI Dictionary |
| ALiBi | Position handling that biases attention scores by distance instead of adding position embeddings. | authored |
| Alignment | Making a model's behavior match human intent and values. | QuKaiZen AI Dictionary |
| Apply warmup schedule | Ramp the LR from near-zero to peak over N steps before the main schedule. | HF Trainer docs (warmup_steps, lr_scheduler_type='cosine_with_restarts'); NVIDIA training guide; OLMo training config |
| Arithmetic Intensity | The ratio of compute to memory traffic; it determines whether a workload is compute- or memory-bound. | authored |
| Attention | The mechanism that lets each token weigh and pull information from every other token. | authored |
| Attention Sink | Initial tokens that attention disproportionately fixates on; preserving them stabilizes long/streaming generation. | authored |
| Autoencoder | Encoder-decoder trained to reconstruct its own input — learns a compressed representation. | Goodfellow et al. — Deep Learning ch.14 (autoencoders) |
| Automation | Letting software run repeatable work end-to-end with no human in the loop. | QuKaiZen AI Dictionary |
| AutoResearch | The swarm's brain — it evolves the rubrics every other agent consults. | QuKaiZen AI Dictionary |
| AWQ | Low-bit quantization that protects the small fraction of weights tied to large activations, preserving accuracy. | authored |
| Backprop | The algorithm that computes how to nudge every weight by propagating error gradients backward. | authored |
| BAKED (lifecycle stage) | [ROADMAP] The third stage of the QuKaiZen knowledge lifecycle — RAW → COMPILED → BAKED. | QuKaiZen CLAUDE.md (RAW→COMPILED→BAKED lifecycle); QuKaiZen DAC_ENGINE.md |
| Baseline | A reference result you compare against to judge whether a change actually helped. | authored |
| Batch normalization | Normalizes activations across the batch dimension to stabilize training. | Ioffe & Szegedy — Batch Normalization arXiv:1502.03167; Goodfellow et al. — Deep Learning ch.8 |
| Batch Size | How many training examples are processed before each weight update. | authored |
| Beam Search | A decoding strategy that keeps the top-k partial sequences each step to find a higher-probability output. | authored |
| Benchmark | A standardized test set used to measure and compare model capability. | QuKaiZen AI Dictionary |
| BF16 | A 16-bit float with the same exponent range as FP32 — the default precision for training LLMs. | authored |
| Born-Again Networks | Distill a model into a fresh copy of identical size — the student often beats the teacher. | authored |
| Buddy | ARAIL's local companion agent — a context-aware lab partner you learn alongside, running entirely on your own hardware. | ARAIL |
| Build-time teacher | [BUILT] Frontier model used only during corpus authoring — never at runtime. | QuKaiZen CLAUDE.md ('the frontier model is the build-time teacher, never the runtime'); QuKaiZen VISION.md |
| Byte-Pair Encoding | A subword tokenization that iteratively merges the most frequent character pairs into tokens. | authored |
| Calibration | Running a small representative dataset through a model to set quantization ranges or scales. | authored |
| Catastrophic Forgetting | When fine-tuning on a new task erases capabilities the model previously had. | authored |
| Chain-of-Thought | Prompting a model to show its intermediate steps, which sharply improves reasoning. | QuKaiZen AI Dictionary |
| Checkpoint | A saved snapshot of model weights (and often optimizer state) you can resume or deploy from. | authored |
| Chinchilla Scaling | The finding that, for a fixed compute budget, model size and training tokens should grow together. | authored |
| Class imbalance | Training data is dominated by a few classes — rare classes are ignored. | Goodfellow et al. — Deep Learning ch.5; PyTorch WeightedRandomSampler docs |
| CoALA | A framework (Princeton, 2023) organizing language agents into memory modules, an action space, and a decision-making loop. | Sumers, Yao, Narasimhan & Griffiths, 'Cognitive Architectures for Language Agents' (2023), arXiv:2309.02427 |
| Constitutional AI | Align a model to an explicit written set of principles, using the model to critique and revise its own outputs. | authored |
| Constrained Decoding | Restrict generation at each step to tokens allowed by a grammar or schema, guaranteeing valid output. | authored |
| Context Window | The maximum number of tokens a model can attend to at once — its working span of input plus output. | authored |
| Continued pretraining | Resume pretraining on domain data before task fine-tuning to build domain fluency. | Gururangan et al. — Don't Stop Pretraining arXiv:2004.10964; HF Trainer docs (language modeling) |
| Continuous Batching | Swapping requests in and out of a running batch every step to keep the GPU saturated. | QuKaiZen AI Dictionary |
| Convergence | Graduation by exhaustion — the model is done when the swarm can't break it anymore. | QuKaiZen AI Dictionary |
| Convergence Graduation | A model graduates when the adversarial swarm gives up trying to break it — not at a fixed cycle limit. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| corpus_sha256 (bake lockfile) | [BUILT] The SHA-256 hash pinning the compiled corpus — the DaC CD lockfile. | QuKaiZen DAC_ENGINE.md (corpus_sha256 = CD lockfile); QuKaiZen CLAUDE.md |
| Cosine Schedule | Decay the learning rate along a cosine curve from its peak down toward zero over training. | authored |
| Cosine Similarity | A measure of how aligned two vectors are by the angle between them — the standard relevance score for embeddings. | authored |
| Cross-Attention | Attention where queries come from one sequence and keys/values from another. | authored |
| Cross-Entropy | The standard LM loss: penalize the model by the negative log-probability it gave the correct token. | authored |
| CUDA | NVIDIA's platform/language for general-purpose GPU computing — the substrate most ML runs on. | authored |
| CUDA Graphs | Capture a fixed sequence of GPU operations once and replay it, eliminating per-step launch overhead. | authored |
| Curriculum Learning | Train on easier examples first, then progressively harder ones, like a teaching syllabus. | authored |
| Data Augmentation | Expand or vary training data with label-preserving transformations to improve robustness. | authored |
| Data Contamination | When benchmark or test data leaks into training, inflating scores and invalidating the eval. | authored |
| Data leakage | Validation/test data has leaked into training — metrics are invalid. | Goodfellow et al. — Deep Learning ch.5 (evaluation); HF datasets docs (train/test split) |
| Data Parallelism | Replicate the model across devices, split the batch, and average gradients each step. | authored |
| Dead neurons | ReLU units stuck at zero — never activate, never learn. | Goodfellow et al. — Deep Learning §6.3.1 (ReLU and variants); PyTorch activation docs |
| Decode Phase | The token-by-token generation phase, bottlenecked by memory bandwidth rather than compute. | authored |
| Decoder-Only | The autoregressive transformer design used by most LLMs: predict the next token, attending only to the past. | authored |
| Deep Learning | Machine learning with many-layered neural networks that learn features automatically from raw data. | authored |
| Desired State | The end state you declare; the system's job is to make reality match it. | QuKaiZen AI Dictionary |
| Determinism | Whether a model returns the same output for the same input every time — LLMs are non-deterministic by default. | authored |
| Distillation | Transfer a big teacher model's behavior into a small student model. | authored |
| Distribution shift | Training and deployment data have different distributions — model degrades at inference. | Goodfellow et al. — Deep Learning ch.7; HF docs on domain adaptation |
| Diverging loss | Training loss climbs without bound instead of decreasing. | PyTorch amp docs; OLMo training logbook (EleutherAI/OLMo, 2024) |
| Documentation as Code (DaC) | QuKaiZen's framework: a declarative, curated source of truth that compiles into a knowledge app or bakes into a model you own. | QuKaiZen |
| Domain Adaptation | Specialize a general model to a target domain, often via continued pretraining on domain text. | authored |
| Domain-specialist model | A model adapted to excel in one domain by fine-tuning, distillation, and domain-adaptive pretraining. | Gururangan et al. — Don't Stop Pretraining arXiv:2004.10964; HF domain adaptation docs; OLMo (EleutherAI) domain specialist experiments |
| DoRA | A LoRA refinement that decomposes weight updates into magnitude and direction for better quality. | authored |
| Double Quantization | Quantize the quantization constants themselves to squeeze out extra memory, as in QLoRA. | authored |
| DPO | Align to preferences directly from good/bad answer pairs — no reward model or RL loop. | authored |
| Draft Model | The small, fast model that proposes candidate tokens in speculative decoding. | QuKaiZen AI Dictionary |
| Drift | When the real state of a system diverges from its declared desired state over time. | authored |
| Dropout | Randomly zeroing activations during training to prevent overfitting. | authored |
| Duplicate / contaminated data | Training data contains repeated or benchmark-contaminated examples. | Lee et al. (2022) — Deduplicating Training Data Makes Language Models Better; OLMo data pipeline docs |
| Early Stopping | Halt training when validation performance stops improving, to avoid overfitting. | authored |
| Ed25519 | A fast, modern public-key signature scheme used to cryptographically sign and verify artifacts. | authored |
| EMA | Exponential moving average of weights kept alongside training for a smoother, often better, final model. | authored |
| Embedding layer | Maps discrete token IDs to dense vectors — the model's vocabulary lookup table. | Goodfellow et al. — Deep Learning ch.12; HF Transformers model architecture docs |
| Embeddings | Dense numeric vectors representing tokens or text so similar meanings sit close together. | authored |
| Emergent Abilities | Capabilities that appear only past a certain model scale, absent in smaller models. | authored |
| Encoder-Decoder | A two-stack design: an encoder reads the full input, a decoder generates output attending to it via cross-attention. | authored |
| Episodic Memory | An agent's memory of specific past experiences — what happened, when, in which session. | authored |
| Epoch | One full pass of the optimizer over the entire training dataset. | authored |
| Eval | The practice of measuring model quality with repeatable tests — from public benchmarks to task-specific graders. | authored |
| Experiment | A single tracked training or evaluation run with a fixed configuration, used to test one change against a baseline. | authored |
| Expert Routing | How a sparse MoE assigns each token to a subset of experts so only part of the model runs per token. | authored |
| Exploding gradients | Gradient norms spike to very large values, destabilizing updates. | Goodfellow et al. — Deep Learning §10.7 (gradient clipping); PyTorch torch.nn.utils.clip_grad_norm_ docs |
| Faithfulness | Whether a model's output is actually supported by its inputs or stated reasoning — not just plausible. | authored |
| Feed-Forward Network | The per-token two-layer MLP in each transformer block, where most parameters and stored knowledge live. | authored |
| Few-Shot | Prompting a model with a handful of worked examples to demonstrate the desired task. | authored |
| Fine-tune | Continue training a pretrained model on new data to specialize it for a task or domain. | authored |
| Fine-tuning | Adapt a pretrained model to a target task or domain by continued gradient updates. | Goodfellow et al. — Deep Learning ch.15 (transfer learning); HF Trainer docs; LoRA arXiv:2106.09685 |
| FlashAttention | An exact attention kernel that is fast and memory-light by never materializing the full attention matrix. | authored |
| Float precision loss | Accumulated rounding errors degrade model quality over many steps. | PyTorch AMP docs (fp32 master weights); NVIDIA mixed-precision guide |
| FLOPs | Floating-point operations — the raw arithmetic count used to measure model and training cost. | authored |
| fp16 overflow (loss scale overflow) | fp16's limited dynamic range causes activations or gradients to overflow to inf. | PyTorch AMP GradScaler docs (pytorch.org/docs/stable/amp.html); NVIDIA mixed-precision guide |
| FP8 | An 8-bit floating-point format for faster training and inference on H100-class hardware. | authored |
| FSDP | Shards model parameters, gradients, and optimizer state across GPUs so huge models fit in training. | authored |
| Function Calling | A structured protocol for a model to request a specific tool with typed arguments. | QuKaiZen AI Dictionary |
| Gating Network | The router in a mixture-of-experts that decides which experts handle each token. | authored |
| GELU | A smooth activation function used in transformer feed-forward layers. | authored |
| Generalization | How well a model performs on new, unseen data rather than the data it trained on. | authored |
| Generative adversarial network (GAN) | Generator and discriminator trained adversarially — generator fools the discriminator. | Goodfellow et al. — Generative Adversarial Networks arXiv:1406.2661; Goodfellow et al. — Deep Learning ch.20 |
| GGML | The C/C++ tensor library underpinning llama.cpp, enabling efficient CPU and edge inference. | authored |
| GGUF | A single-file binary format for quantized models, built for fast local inference (llama.cpp). | authored |
| GPTQ | A one-shot, layer-by-layer post-training quantization method that minimizes per-layer error using second-order info. | authored |
| Gradient | The vector of partial derivatives telling how the loss changes as you tweak each weight. | authored |
| Gradient Accumulation | Sum gradients over several micro-batches before updating, simulating a large batch on limited memory. | authored |
| Gradient Clipping | Cap the gradient's magnitude each step to prevent exploding updates from destabilizing training. | authored |
| Gradient Descent | The core optimization: repeatedly step parameters in the direction that most reduces the loss. | authored |
| Gradient noise | High-variance gradient estimates slow convergence and require larger batches or LR tuning. | Goodfellow et al. — Deep Learning ch.8; Karpathy nanoGPT notes |
| Greedy Decoding | Always pick the single highest-probability next token — deterministic but can be repetitive. | authored |
| Grounding | Connecting an agent's language to the real world via tools, environments, or retrieved facts. | authored |
| Grouped-Query Attention | Share key/value heads across groups of query heads to shrink the KV-cache with little quality loss. | authored |
| GRPO | A PPO-style RL method that drops the value network, scoring each sample relative to a group of samples for the same prompt. | authored |
| GSM8K | Around 8,500 grade-school math word problems that test multi-step arithmetic reasoning. | authored |
| Guardrails | Runtime checks around a model that block, filter, or reshape unsafe inputs and outputs. | authored |
| Hallucination | When a model states fluent, confident information that is fabricated or unsupported. | authored |
| HalluLens | A benchmark for measuring how often an LLM hallucinates — asserts unsupported or fabricated facts. | authored |
| Handoff | Passing control and context from one agent to another so work continues without losing state. | authored |
| HELM | Stanford's broad, multi-metric benchmark suite that scores models across many scenarios, not just accuracy. | authored |
| HHH | The 'helpful, honest, harmless' framing of what an aligned assistant should be. | authored |
| Hidden State | The vector a model holds for each token at each layer — its evolving internal representation. | authored |
| Hugging Face | The hub and libraries (Transformers, Datasets, Hub) that are the de facto registry for open models. | authored |
| Hypothesis | A testable prediction you set out to confirm or refute with an experiment. | QuKaiZen AI Dictionary |
| IA3 | An extremely lightweight PEFT method that learns to rescale activations with a few vectors. | authored |
| Idempotent | An operation that produces the same result whether applied once or many times. | authored |
| IFEval | A benchmark of machine-verifiable instructions that measures how precisely a model obeys format and constraint requests. | authored |
| In-Context Learning | A model learns a task from examples in its prompt at inference time, with no weight updates. | authored |
| Increase batch size / accumulation | Use a larger effective batch size to stabilize gradient estimates and improve throughput. | PyTorch gradient accumulation pattern; HF Trainer docs (per_device_train_batch_size, gradient_accumulation_steps); NVIDIA performance guide |
| Inference | Running a trained model to produce outputs — the deployment side, as opposed to training. | authored |
| Instruction Tuning | Fine-tune a base model on instruction-response pairs so it follows natural-language commands. | authored |
| INT4 | 4-bit integer weights — the aggressive quantization that makes big models fit on small hardware. | knowledge_base/wiki/concepts/Quantization_SNR_Affine.md |
| INT8 | 8-bit integer representation — a common, low-risk quantization that roughly halves memory versus 16-bit. | authored |
| Internal covariate shift | Distribution of layer activations shifts during training, slowing convergence. | Ioffe & Szegedy — Batch Normalization arXiv:1502.03167; Goodfellow et al. — Deep Learning §8.7 |
| IPO | A DPO variant that adds regularization to avoid overfitting to deterministic preferences. | authored |
| Jailbreak | An input crafted to bypass a model's safety training and elicit disallowed behavior. | authored |
| K-Quants | The GGUF family of mixed-bit quantization schemes that allocate more bits to important weights. | authored |
| Kernel Fusion | Combine multiple GPU operations into one kernel to cut memory round-trips and launch overhead. | authored |
| KICE | QuKaiZen's agent that extracts certified, verifiable domain knowledge in six layers. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| KL Divergence | A measure of how far one distribution is from another — used to keep an RL-tuned model near its base. | authored |
| Knowledge Base | An external, queryable store of facts and documents a model retrieves from instead of relying on weights alone. | authored |
| Knowledge distillation | Transfer knowledge from a large teacher model to a smaller student model. | Hinton et al. — Distilling the Knowledge in a Neural Network arXiv:1503.02531; Goodfellow et al. — Deep Learning ch.7 |
| KTO | Preference alignment from simple good/bad labels rather than paired comparisons. | authored |
| KV-Cache | Cached key/value tensors from past tokens so generation does not recompute the whole sequence each step. | authored |
| Label Smoothing | Soften one-hot targets slightly so the model doesn't become over-confident. | authored |
| Latency | The delay before and during a model's response — time-to-first-token and per-token time. | QuKaiZen AI Dictionary |
| Latent Space | The learned, compressed vector space in which a model represents meaning. | authored |
| Layer normalization | Normalizes activations across the feature dimension within each example. | Ba et al. — Layer Normalization arXiv:1607.06450; Goodfellow et al. — Deep Learning ch.8 |
| Layer Streaming | Load one transformer layer from disk, compute, discard — running 400B+ models on tiny VRAM. | knowledge_base/wiki/concepts/Layer_Streaming_Inference.md |
| LayerNorm | Normalizes activations within each layer to keep training stable; modern LLMs often use RMSNorm. | authored |
| Learning Rate | How big a step the optimizer takes down the gradient — the most consequential training hyperparameter. | authored |
| Learning rate schedule | A plan for how the learning rate changes over the course of training. | HF Trainer docs (lr_scheduler_type, warmup_ratio); Goodfellow et al. — Deep Learning ch.8; NVIDIA training guide |
| Learning rate too high | Peak LR exceeds what the schedule/optimizer can stabilize. | HF Trainer docs (lr_scheduler_type, warmup_steps); Goodfellow et al. ch.8; OLMo logbook |
| Learning rate too low | LR is so small that the optimizer barely moves — training stalls. | HF Trainer docs; Goodfellow et al. — Deep Learning ch.8 (hyperparameter tuning) |
| llama.cpp | A lean C/C++ inference engine that runs quantized LLMs efficiently on CPUs, Macs, and modest GPUs. | authored |
| LLM | A transformer trained on vast text to predict the next token, yielding broad language ability. | QuKaiZen AI Dictionary |
| Logits | The model's raw, unnormalized output scores over the vocabulary, before softmax makes them probabilities. | authored |
| Long-Term Memory | An agent's durable store that survives across sessions, beyond the context window. | authored |
| LoRA | Fine-tune a model by training tiny low-rank adapter matrices while the base weights stay frozen. | qukaizen/docs/TECHNIQUES.md |
| Loss Function | The scalar that measures how wrong a model's predictions are — what training minimizes. | authored |
| Loss plateau | Loss stops improving for many steps — training is stalled. | Goodfellow, Bengio & Courville — Deep Learning ch.8; HF Trainer docs (lr_scheduler_type) |
| Loss spike | A sharp, transient jump in loss that may or may not recover. | OLMo training logbook; Karpathy nanoGPT notes on loss spikes |
| MCP | An open standard for connecting models to tools and data sources. | QuKaiZen AI Dictionary |
| Memory Bandwidth | How fast data moves between memory and compute — the usual bottleneck for LLM inference. | authored |
| Memory Stream | A time-ordered log of an agent's observations, scored by recency, importance, and relevance for retrieval. | authored |
| MFU | Model FLOPs Utilization — the fraction of a chip's peak FLOP/s your training actually achieves. | authored |
| Mixed Precision | Use lower precision for most math but keep sensitive parts in higher precision for stability. | authored |
| Mixed-precision training | Use fp16 or bf16 for forward/backward passes while keeping fp32 master weights. | PyTorch AMP docs (torch.cuda.amp); NVIDIA mixed-precision training guide; HF Trainer docs (fp16, bf16) |
| MLX | Apple's array framework for running and training models on Apple Silicon's unified memory. | QuKaiZen AI Dictionary |
| MMLU | A benchmark of ~16,000 multiple-choice questions across 57 subjects, measuring an LLM's breadth of knowledge. | authored |
| Mode collapse | Generator produces only a few outputs — diversity collapses. | Goodfellow et al. — Deep Learning ch.20 (generative models, GANs); RLHF literature (reward hacking) |
| Model Merging | Combine multiple fine-tuned models into one by arithmetic on their weights, no extra training. | authored |
| MoE | A model split into many expert sub-networks where a router activates only a few per token. | authored |
| Multi-Agent | Several specialized agents collaborating, each owning a function. | QuKaiZen AI Dictionary |
| Multi-Head Attention | Run several attention operations in parallel, each in its own subspace, then concatenate. | authored |
| Multi-Query Attention | All query heads share a single key/value head — the most aggressive KV-cache reduction. | authored |
| Multimodal | Models that take in or produce more than one kind of data — text, images, audio, video. | authored |
| N-gram | A contiguous sequence of n tokens; the basis of pre-neural language models and still used for metrics. | authored |
| NaN loss | Loss value becomes Not-a-Number — the run is numerically broken. | PyTorch AMP / GradScaler docs (pytorch.org/docs/stable/amp.html); NVIDIA mixed-precision guide |
| Neural Network | Layers of simple weighted units that transform inputs into outputs, learning the weights from data. | authored |
| NF4 | A 4-bit 'normal float' data type, used in QLoRA, tuned for the bell-curve distribution of weights. | authored |
| Noisy labels | Training data contains incorrectly labeled examples — the model learns corrupted signal. | Goodfellow et al. — Deep Learning ch.7 (regularization against label noise); HF datasets quality guides |
| Nucleus (bake engine) | [ROADMAP] QuKaiZen's training pipeline for baking domain-specialist SLMs. | QuKaiZen CLAUDE.md (Nucleus: company hub, bake pipeline); QuKaiZen THEME.md; QuKaiZen VISION.md |
| Nucleus Seal | An Ed25519 cryptographic provenance chain proving how a Super Skill model was made. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| Numerical overflow | Values exceed the representable range and become inf — NaN propagates downstream. | PyTorch AMP docs; NVIDIA mixed-precision guide |
| Numerical underflow | Values become too small to represent and round to zero — silent precision loss. | PyTorch numerical stability docs; NVIDIA mixed-precision guide (numerical formats) |
| Ollama | A local runtime that packages and serves models with one command, built on llama.cpp. | authored |
| Online Distillation | Teacher and student train together at the same time instead of distilling from a frozen teacher. | authored |
| ONNX | An open, framework-neutral format for exchanging models between training and inference runtimes. | authored |
| Orchestration | Coordinating multiple agents or services into one coherent flow. | QuKaiZen AI Dictionary |
| ORPO | A single-stage method that combines instruction tuning and preference alignment without a separate reward model or reference model. | authored |
| Oscillating loss | Loss bounces between high and low values without a clear downward trend. | Goodfellow et al. — Deep Learning ch.8 (learning rate); PyTorch optimizer docs |
| Out-of-memory (OOM) error | GPU runs out of VRAM — the process crashes with a CUDA OOM. | PyTorch memory docs; HF Trainer docs (fp16, gradient_accumulation_steps); NVIDIA deep-learning performance guide |
| Overfitting | When a model memorizes training-set quirks and fails to generalize to new data. | authored |
| PagedAttention | Storing the KV-cache in non-contiguous pages so long contexts fit without waste. | QuKaiZen AI Dictionary |
| Parameter | A single learned number in a model; their count (e.g. 7B) is the rough measure of model size. | authored |
| PEFT | An umbrella for methods (LoRA, adapters, prefix-tuning) that tune a tiny fraction of parameters. | authored |
| Perplexity | A measure of how surprised a model is by text — lower means it predicts the text better. | authored |
| Pipeline Parallelism | Place different layers on different devices and stream micro-batches through them like an assembly line. | authored |
| Planning | An agent breaks a goal into an ordered set of subtasks before (or while) acting. | authored |
| Positional Encoding | Information added to tokens so the otherwise order-blind transformer knows their sequence positions. | authored |
| Post-training quantization | Quantize a trained model without further training — fast but some quality loss. | Frantar et al. — GPTQ arXiv:2210.17323; bitsandbytes (load_in_4bit) docs |
| Posterior collapse | VAE latent variables collapse to the prior — the encoder becomes useless. | Bowman et al. (2016) — Generating Sentences from a Continuous Space (posterior collapse identification); Goodfellow et al. — Deep Learning ch.20 |
| PPO | The RL algorithm classically used to optimize a model against a reward model in RLHF. | authored |
| Preference Data | Datasets of 'A is better than B' human judgments used to train reward models or do DPO. | authored |
| Prefetch | Loading the next layer from disk while the current compute runs, hiding I/O latency. | QuKaiZen AI Dictionary |
| Prefill | The compute-heavy first phase where the model ingests the whole prompt in parallel. | authored |
| Prefix Tuning | Prepend trainable key/value vectors to every layer's attention, freezing the base model. | authored |
| Pretraining | The first, largest training stage: learn general language/knowledge from a huge unlabeled corpus. | authored |
| Procedural Memory | An agent's memory of how to do things — its skills, routines, and the agent code itself. | authored |
| Process Reward Model | A reward model that scores each step of a reasoning chain, not just the final answer. | authored |
| Prompt | The input text you give a model to steer what it does. | QuKaiZen AI Dictionary |
| Prompt Caching | Provider-side cache that bills a repeated prompt prefix at a fraction of fresh-input cost on cache hit. | authored |
| Prompt Injection | An attack where untrusted input smuggles instructions that override the system's intended ones. | authored |
| Prompt Tuning | Learn a small set of continuous 'soft prompt' vectors while freezing the model, to steer behavior cheaply. | authored |
| Provenance | A verifiable record of exactly what went into a model and how it was built. | QuKaiZen AI Dictionary |
| PyTorch | The dominant deep-learning framework for research and much production, built on eager Python tensors. | authored |
| QAT | Quantization-aware training: simulate low precision during training so the model learns to tolerate it. | authored |
| QLoRA | LoRA on top of a 4-bit quantized base model — fine-tune big models on one consumer GPU. | authored |
| Quantization | Storing weights/activations in fewer bits (FP16 to INT4) to shrink models and speed inference. | knowledge_base/wiki/concepts/Quantization_SNR_Affine.md |
| Quantization-aware training | Train with simulated quantization so the model adapts to the reduced precision. | Jacob et al. — Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference arXiv:1712.05877; PyTorch quantization docs |
| RAFT | Fine-tuning that teaches a model to reason over retrieved docs while ignoring distractors. | knowledge_base/wiki/concepts/RAFT.md |
| RAG | Fetch relevant documents at query time and feed them to the model as context. | QuKaiZen AI Dictionary |
| ReAct | An agent pattern that interleaves reasoning steps ('thoughts') with actions ('tool calls') in a loop. | authored |
| Reasoning | A model working through a problem in intermediate steps instead of answering in one leap. | QuKaiZen AI Dictionary |
| Reconciliation | Continuously closing the gap between the team you declared and the team that's running. | QuKaiZen AI Dictionary |
| Red-Teaming | Deliberately probing a model with adversarial inputs to surface harmful, unsafe, or broken behavior. | authored |
| Reduce learning rate | Lower the peak LR (and/or lengthen warmup) to restabilize. | HF Trainer docs (learning_rate, warmup_steps); NVIDIA training-performance guide; OLMo logbook |
| Reflection | An agent reviews its own past actions or outputs and writes higher-level lessons or corrections. | authored |
| Reflexion | An agent loop that converts failure feedback into written self-reflection stored in memory for the next attempt. | authored |
| Regularization | Any technique that constrains a model to generalize better rather than memorize the training set. | authored |
| Rejection-Sampling Fine-Tuning | Sample many answers, keep only the ones that pass a check, then fine-tune on the survivors. | authored |
| ReLU | Rectified Linear Unit — max(0, x). The most common hidden-layer activation. | Goodfellow et al. — Deep Learning §6.3.1; PyTorch ReLU docs |
| Repetition Penalty | A decoding adjustment that lowers the probability of tokens already generated, reducing loops. | authored |
| Research | Systematic inquiry — forming hypotheses, running experiments, and measuring results. | QuKaiZen AI Dictionary |
| Residual Connection | Add a layer's input to its output so gradients and signal can flow straight through deep stacks. | authored |
| Resume from checkpoint | Roll back to a saved state before the failure and restart with corrected hyperparameters. | HF Trainer docs (resume_from_checkpoint, save_steps); PyTorch checkpoint docs |
| Reward Hacking | When a model maximizes the reward signal in unintended ways that don't reflect true quality. | authored |
| Reward Model | A model trained to score outputs by human preference, providing the reward signal for RLHF. | authored |
| RLAIF | Like RLHF, but the preference labels come from an AI judge instead of (or alongside) humans. | authored |
| RLHF | Align a model to human preferences via a reward model trained on human rankings, then RL. | authored |
| RMSNorm | A lighter normalization that scales activations by their root-mean-square, without subtracting the mean. | authored |
| RoPE | Encodes token position by rotating query/key vectors — the dominant positional scheme in modern LLMs. | authored |
| Rubric | The evolving scoring criteria AutoResearch uses to probe and grade the student. | QuKaiZen AI Dictionary |
| SafeTensors | A safe, fast, zero-copy tensor file format — the modern replacement for pickle-based checkpoints. | authored |
| Sampling | Drawing the next token randomly from the model's probability distribution rather than always taking the top one. | authored |
| Scaling Laws | Empirical power-law curves showing model loss falls predictably as parameters, data, and compute grow. | authored |
| SCoTD | Distill a teacher's step-by-step reasoning into a small model via many symbolic CoT traces. | knowledge_base/wiki/concepts/SCoTD.md |
| Seal | A cryptographic signature certifying a model's provenance — what it was distilled from and that it is untampered. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| Self-attention | Each token attends to all other tokens in the sequence to build context-aware representations. | Vaswani et al. — Attention Is All You Need arXiv:1706.03762 |
| Self-Consistency | Sample several reasoning chains and take the majority answer, trading compute for accuracy. | authored |
| Self-Distillation | A model acts as its own teacher — its current outputs become training targets for a refined version of itself. | authored |
| Self-Supervised Learning | Create the training signal from the data itself — e.g. predict the next token — needing no human labels. | authored |
| Semantic Memory | An agent's store of general world knowledge and facts, decoupled from any single experience. | authored |
| SentencePiece | A language-agnostic tokenizer toolkit that trains subword models directly on raw text. | authored |
| SFT | Plain supervised training on curated input to output examples — the first step of post-training. | authored |
| SGD | Stochastic gradient descent: estimate the gradient from a small random batch instead of the whole dataset. | authored |
| Sliding-Window Attention | Each token attends only to a fixed window of nearby tokens, making attention linear in length. | authored |
| Slow convergence | Loss decreases, but far more slowly than expected for the compute budget. | Goodfellow et al. — Deep Learning ch.8; HF Trainer docs; OLMo training logbook |
| Small language model (SLM) | A language model small enough to run on consumer hardware — typically 1B–13B parameters. | Goodfellow et al. — Deep Learning (model compression); HF model hub SLM examples; NVIDIA deep-learning performance guide |
| SmoothQuant | Shift quantization difficulty from activations to weights so both can go to INT8 cleanly. | authored |
| Soft Targets | A teacher's full probability distribution used as the training target, not just the single correct label. | authored |
| Softmax | Turns a vector of logits into a probability distribution that sums to 1. | authored |
| Sparse Attention | Compute attention over only a chosen subset of token pairs instead of all of them. | authored |
| Speculative Decoding | A small draft model proposes several tokens; the big model verifies them in one pass — lossless speedup. | knowledge_base/wiki/concepts/speculative-decoding.md |
| SSDP | QuKaiZen's pipeline that distills deep reasoning from frontier teacher models into small, owned Super Skill models. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| Stale / mismatched checkpoint | Loading a checkpoint whose architecture or tokenizer does not match the current code. | HF Transformers docs (from_pretrained, config matching); OLMo checkpoint management docs |
| State-Space Model | A sequence architecture that carries a recurrent hidden state, scaling linearly with length instead of attention's quadratic cost. | authored |
| Stop Sequence | A string that, once generated, halts decoding — used to bound output and separate turns. | authored |
| Structured Output | Forcing a model's response into a machine-parseable shape like JSON conforming to a schema. | authored |
| Student Model | The small model being trained to absorb the teacher's reasoning. | QuKaiZen AI Dictionary |
| Super Skill | A 1-7B model that durably knows a domain, distilled from a frontier teacher and owned forever. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| Supervised Learning | Learning from labeled examples — inputs paired with the correct outputs. | authored |
| Supervisor Agent | An orchestrating agent that routes work to specialist sub-agents and integrates their results. | authored |
| SwiGLU | A gated activation for the feed-forward block that tends to beat plain GELU/ReLU at equal size. | authored |
| Switch optimizer | Change the optimizer (e.g., SGD → Adam, Adam → AdamW) to better fit the problem. | AdamW: Loshchilov & Hutter arXiv:1711.05101; HF Trainer docs (optim=adamw_hf); PyTorch optimizer docs |
| Sycophancy | A model's tendency to tell users what they want to hear rather than what's true. | authored |
| Symbolic Chain-of-Thought | Capturing a teacher's reasoning as reusable symbolic structure, not just imitated text traces. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| System Prompt | A high-priority instruction block that sets a model's role, rules, and behavior before the user's turn. | authored |
| Task Arithmetic | Treat the weight change from fine-tuning as a 'task vector' you can add or subtract. | authored |
| Teacher Model | The large frontier model whose reasoning is distilled into a small student. | QuKaiZen AI Dictionary |
| Teacher–student training | A large teacher model guides a smaller student model's training. | Hinton et al. — Distilling the Knowledge arXiv:1503.02531; HF trl docs (knowledge distillation) |
| Temperature | A knob for randomness in generation — low is focused/deterministic, high is creative/diverse. | authored |
| Tensor Parallelism | Split individual weight matrices across devices so one layer's math is computed in parallel. | authored |
| TensorRT | NVIDIA's inference optimizer/runtime that compiles models into highly tuned GPU engines. | authored |
| TGI | Hugging Face's production inference server for high-throughput, low-latency LLM serving. | authored |
| The bake (sealed specialist SLM) | [ROADMAP] The sealed domain-specialist SLM produced by the Nucleus pipeline — the one bet. | QuKaiZen CLAUDE.md ('the bake is the moat', 'the one bet'); QuKaiZen THEME.md; QuKaiZen VISION.md |
| Throughput | How many tokens a system generates per unit time, across all requests. | QuKaiZen AI Dictionary |
| TICE | QuKaiZen's agent for Layer-7 tacit knowledge — the unwritten expert know-how and gotchas. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| TIES-Merging | A merge recipe that trims small changes and resolves sign conflicts between task vectors. | authored |
| Tokenization mismatch | Tokenizer and model are mismatched — inputs are decoded/encoded incorrectly. | HF Transformers tokenizer docs (AutoTokenizer.from_pretrained); OLMo tokenizer documentation |
| Tokenizer | Splits text into tokens (subword units) the model actually reads, and back again. | authored |
| Tool Use | A model invoking external tools — APIs, code, search — to act beyond text. | QuKaiZen AI Dictionary |
| Top-k Sampling | Restrict sampling to the k most probable next tokens, then renormalize and draw from those. | authored |
| Top-p (Nucleus) Sampling | Sample from the smallest set of top tokens whose probabilities sum to p — an adaptive cutoff. | authored |
| torch.compile | PyTorch's just-in-time compiler that traces and optimizes a model into faster fused kernels. | authored |
| Train/val loss gap | Validation loss significantly worse than training loss — generalization failure. | Goodfellow et al. — Deep Learning ch.7 (regularization); HF Trainer docs (evaluation_strategy) |
| Transfer Learning | Reuse a model trained on one task as the starting point for another, instead of training from scratch. | authored |
| Transformer | The attention-based neural architecture behind essentially every modern LLM. | authored |
| Tree of Thoughts | Explore multiple reasoning branches as a search tree, evaluating and backtracking, instead of one chain. | authored |
| Tri-Attention | Attention that adds an explicit third 'context' term to the usual query-key interaction, modeling three-way relationships instead of pairwise ones. | authored |
| Triton | A Python-like language for writing fast GPU kernels without hand-writing CUDA C++. | authored |
| TTFT | Time to first token — how long after a request before the model emits its first output token. | authored |
| Unsupervised Learning | Finding structure in data with no labels — clustering, density, or representation. | authored |
| Validation Set | Held-out data used to tune and monitor training, kept separate from the final test set. | authored |
| Vanishing gradients | Gradients shrink toward zero in early layers — no useful learning signal. | Goodfellow et al. — Deep Learning §10.7; Karpathy nanoGPT architectural notes |
| Variational autoencoder (VAE) | A generative model that learns a probabilistic latent space via the ELBO objective. | Kingma & Welling — Auto-Encoding Variational Bayes arXiv:1312.6114; Goodfellow et al. — Deep Learning ch.20 |
| Verifier | The target-model pass that accepts or corrects speculatively drafted tokens. | QuKaiZen AI Dictionary |
| Vision Transformer | A transformer that processes images by splitting them into patches treated as tokens. | authored |
| vLLM | A high-throughput LLM serving engine; its PagedAttention manages the KV-cache like virtual memory. | qukaizen/docs/TECHNIQUES.md |
| Vocabulary | The fixed set of tokens a model knows; its size sets the width of the input and output layers. | authored |
| Warmup | Ramping the learning rate up from near zero over the first steps to avoid early instability. | authored |
| Watcher | A process that observes for changes and triggers reconciliation when state moves. | authored |
| Weight Decay | A penalty that nudges weights toward zero each step, discouraging overly large parameters and overfitting. | authored |
| Weight initialization | How weights are set before training — a critical determinant of early convergence. | He et al. — Delving Deep into Rectifiers arXiv:1502.01852; Glorot & Bengio (2010) — Understanding Difficulty of Training Deep FFNs; Goodfellow et al. — Deep Learning §8.4 |
| Wisdom per Watt | QuKaiZen's core metric: certified, permanently-owned reasoning capability per unit of lifetime energy to mint and run it. | QuKaiZen NUCLEUS_AGENT_PROTOCOL |
| Workflow | A declared sequence of steps an agent or pipeline executes. | QuKaiZen AI Dictionary |
| Working Memory | An agent's active scratchpad — the small, volatile state it holds for the current decision. | authored |
| YaRN | A method to extend a model's usable context window by rescaling its rotary position frequencies. | authored |
| ZeRO | DeepSpeed's optimizer that partitions optimizer state, gradients, and params to remove memory redundancy. | authored |
| Zero-Shot | Asking a model to perform a task from instructions alone, with no examples. | authored |
