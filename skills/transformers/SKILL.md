# transformers

description: Hugging Face Transformers/Datasets/PEFT for LLM & vision work — loading, inference, tokenization, dataset pipelines.

## When to use
Working with pretrained LMs, embeddings, vision models, tokenization, or HF datasets.

## How
1. In sandbox (HF cache is /workspace/.hf — visible on host):
   ```python
   from transformers import AutoModelForCausalLM, AutoTokenizer
   tok = AutoTokenizer.from_pretrained("HuggingFaceTB/SmolLM2-135M-Instruct")  # tiny test model
   model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float16).cuda()
   ids = tok("Hello", return_tensors="pt").to("cuda")
   out = model.generate(**ids, max_new_tokens=50)
   ```
2. Sizes that fit 8 GB (fp16): ≤ ~1B params comfortably (2 GB + activations); 3B with small context; 7B only for inference at short context, no training.
3. Datasets: load_dataset("csv", data_files="...") for local; cache under /workspace/.hf.
4. For serving LLMs locally, prefer Ollama (host) — transformers is for custom pipelines.

## Gotchas
- First download hits the network inside Docker (needs internet) or pre-pull weights on host and mount them.
- float16 is default on this card; float32 doubles VRAM.
- generate() with do_sample=False for deterministic outputs (evals).
- Always check model.card for expected context length before long prompts.
