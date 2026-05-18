# Model tiers

Hardware, model, and performance guidance for the local LLMs dos-arch
shells run against. A working doc — the model picks are current and the
hardware classes are stable; the performance notes are seeded and meant to
grow with measured numbers.

See **[install/README.md → Local models](../install/README.md#local-models)**
for installing Ollama and recording hardware/models in the DB. Browse every
available model at **[ollama.com/library](https://ollama.com/library)**.

## How to read this

The hard constraint is **VRAM** (or, on unified-memory machines, the memory
share the GPU can use). A model whose weights fit entirely in VRAM runs at
full speed; one that spills into system RAM or onto the CPU runs many times
slower.

- **Quantization** — all sizes below assume **Q4** (Ollama's default). Q4 is
  the sweet spot: ~4–5 GB for a 7–8B model, minimal quality loss. Higher
  precision (Q6/Q8) is larger and slower; lower (Q3/Q2) degrades noticeably.
- **Headroom rule** — budget roughly **on-disk size + ~1.5 GB** of VRAM
  (weights + KV cache + runtime). A 4.7 GB model wants ~6.5 GB free.
- **Param ceiling** — each tier lists the largest parameter count that fits
  comfortably at Q4. Bigger is generally better; staying in-VRAM matters more.

dos-arch records this automatically: `collect_hardware.py` buckets a
machine's VRAM into a `vram_tier` on `user_hardware`; `model_sync.py`
stamps a `min_vram_gb` on each row in `models`. Joining the two shows which
installed models a given host can actually run on the GPU.

---

## 8 GB — ~7–8B ceiling

**Typical hardware:** RTX 4060 / 4070 laptop, RTX 3060 Ti, RTX 3070,
Intel Arc A770 8 GB.

| Model | Use |
|---|---|
| `qwen2.5-coder:7b` | Coding workhorse |
| `qwen2.5-coder:3b` | Fast/light code |
| `qwen3:8b` | General + reasoning mode |
| `llama3.1:8b` | General-purpose baseline |
| `mistral` | Fast general-purpose |
| `gemma3:4b` | Light, multimodal |
| `deepseek-r1:8b` | Chain-of-thought reasoning |
| `phi4-mini` | Lightest quick tasks |

**Notes:** the practical floor for useful coding work. One ~7–8B model
occupies VRAM at a time — Ollama auto-unloads on switch. Small models need
tight, explicit prompts; they infer less than hosted frontier models.

---

## 12 GB — ~14B ceiling

**Typical hardware:** RTX 3060 12 GB, RTX 4070 desktop, RTX 5070.

| Model | Use |
|---|---|
| `mistral-nemo:12b` | Strong general-purpose |
| `qwen2.5-coder:14b` | Bigger coding model |
| `qwen3:14b` | General + reasoning |
| `phi4` | Microsoft's 14B reasoning model |
| `gemma3:12b` | General, multimodal |
| `deepseek-r1:14b` | Larger reasoning distill |

**Notes:** the 14B class is a real step up in instruction-following over
8B. Everything from the 8 GB tier also runs here, with more context room.

---

## 24 GB — ~32B ceiling

**Typical hardware:** RTX 3090, RTX 4090, RTX A5000.

| Model | Use |
|---|---|
| `qwen2.5-coder:32b` | Top-tier local coding |
| `qwen3:32b` | Strong general + reasoning |
| `codestral:22b` | Mistral's code model |
| `devstral` | Mistral's agentic coder (24B) |
| `mistral-small` | Mistral's 24B general model |
| `gemma3:27b` | Largest Gemma 3 |

**Notes:** `qwen2.5-coder:32b` is the first local model genuinely
competitive for sustained coding work. The 24 GB class is the sweet spot
for a single-GPU local-LLM box.

---

## 32 GB — ~32B with headroom, or MoE

**Typical hardware:** RTX 5090, or dual mid-range cards.

| Model | Use |
|---|---|
| `qwen2.5-coder:32b` | Coding, with large context headroom |
| `qwen3:32b` | General + reasoning, long context |
| `mixtral:8x7b` | Mixture-of-experts — fast inference |
| `deepseek-r1:32b` | Large reasoning distill |

**Notes:** the extra 8 GB over the 24 GB tier mostly buys **context
length** — a 32B model with a long context window instead of a cramped
one. Also fits MoE models like `mixtral:8x7b` (only ~2 experts active per
token, so fast for its size).

---

## 48 GB — ~70B ceiling

**Typical hardware:** RTX 6000 Ada, RTX A6000, or 2×24 GB (dual 3090/4090).

| Model | Use |
|---|---|
| `llama3.3:70b` | Flagship general-purpose |
| `deepseek-r1:70b` | Large reasoning distill |
| `qwen2.5-coder:32b` | Coding at full context |
| `mixtral:8x7b` | MoE with generous headroom |

**Notes:** 70B at Q4 is ~40+ GB — this is the entry point for that class.
On a dual-GPU box Ollama splits the model across cards automatically;
expect lower tok/s than a single card holding the whole model.

---

## 128 GB — unified-memory mini PC

**Typical hardware:** Apple Mac mini / Mac Studio (M-series), AMD Ryzen AI
Max ("Strix Halo") mini PCs, NVIDIA DGX Spark. These share one large pool
of **unified memory** between CPU and GPU rather than having dedicated
discrete VRAM.

| Model | Use |
|---|---|
| `llama3.3:70b` | Flagship general-purpose, room to spare |
| `deepseek-r1:70b` | Large reasoning distill |
| `mixtral:8x22b` | Large mixture-of-experts |
| `qwen3:32b` + others | Several models resident at once |

**Notes:** capacity is rarely the limit here — **memory bandwidth** is.
Unified memory is slower than the GDDR/HBM on a discrete GPU, so a 70B
model loads comfortably but generates tokens at a bandwidth-bound rate.
Strong fit for large MoE models (low active-parameter count per token) and
for keeping multiple models loaded simultaneously.

---

## Performance notes

To be filled in with measured `eval rate` (tokens/s) figures per
model × hardware as dos-arch runs on real machines. Capture them from
`ollama run … --verbose` and append here.

| Host | GPU | Model | tok/s | Notes |
|---|---|---|---|---|
| _(add measurements)_ | | | | |
