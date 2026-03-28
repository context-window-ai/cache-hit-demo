# cache-hit-demo

A reproducible benchmark measuring the real-world impact of Anthropic prompt caching through [OpenRouter](https://openrouter.ai), with full observability via [Langfuse](https://langfuse.com).

Three routing configurations. Same model. Same 10 questions. Measured cost, latency, and cache hit rate per turn.

---

## What's being tested

We use the [OpenRouter Python SDK](https://github.com/OpenRouterTeam/openrouter-python) as the context — concatenated into a single string and passed as a system message. Ten code review questions are asked against it in sequence.

| Run | Routing | Caching |
|-----|---------|---------|
| **A** | Anthropic (direct) | ❌ Off |
| **B** | Anthropic (direct) | ✅ On — ephemeral breakpoint |
| **C** | Amazon Bedrock | ✅ On — ephemeral breakpoint |

The `cache_control` breakpoint tells Anthropic's API to store the large context block server-side. Turn 1 is always a cold miss (write). Turns 2–10 hit the warm cache.

---

## Quickstart

**Prerequisites:** Python 3.11+, an [OpenRouter API key](https://openrouter.ai/keys), a [Langfuse Cloud](https://cloud.langfuse.com) project.

```bash
git clone https://github.com/context-window-ai/cache-hit-demo
cd cache-hit-demo

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# → fill in OPENROUTER_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

bash scripts/generate_context.sh   # clone SDK + build codebase_context.txt
python benchmark.py                # run all three sessions (~5–8 min)
python visualize.py                # generate results/benchmark_chart.png
python generate_blog.py            # draft a blog post from your real numbers
```

Results land in `results/`:
```
results/
  cache_benchmark_results.json   # raw per-turn data
  benchmark_chart.png            # 2×2 chart
  blog_post_draft.md             # post template with your actual numbers
```

---

## How caching is wired up

```python
from langfuse.openai import openai   # drop-in, adds Langfuse tracing

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

system_content = [{
    "type": "text",
    "text": f"You are a code review assistant.\n\n{codebase}",
    "cache_control": {"type": "ephemeral"},   # ← the only change vs. Run A
}]

response = client.chat.completions.create(
    model="anthropic/claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ],
    extra_body={"provider": {"order": ["Anthropic"], "allow_fallbacks": False}},
    # Langfuse metadata — intercepted locally, not forwarded to OpenRouter
    session_id="benchmark-run-b",
    metadata={"turn": 2, "use_cache": True},
    tags=["cache-benchmark", "cache-on"],
)

cached = response.usage.prompt_tokens_details.cached_tokens  # 0 on turn 1, >0 after
```

**Validating it works:** check that `cached_tokens > 0` starting from Turn 2. If it's always 0 on cached runs, the `cache_control` field is being stripped before it reaches the API — see the note in `benchmark.py`.

---

## Langfuse observability

Every completion is traced automatically. In your Langfuse dashboard:

- Filter by tag `cache-benchmark` to isolate this experiment
- Group by `session_id` to compare runs A, B, C side-by-side
- Inspect `cached_tokens` per call to verify cache hits
- Compare cost and latency distributions across sessions

---

## Project layout

```
cache-hit-demo/
├── benchmark.py            # main script — runs all three sessions
├── visualize.py            # reads results JSON, produces benchmark_chart.png
├── generate_blog.py        # renders a blog post draft from real results
├── scripts/
│   └── generate_context.sh # clones OpenRouter SDK, builds codebase_context.txt
├── results/                # output directory (gitignored by default)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Customising the benchmark

**Different model:** change `MODEL` in `benchmark.py`. Any Anthropic model on OpenRouter supports `cache_control`.

**Different context:** replace `generate_context.sh` with anything that produces `codebase_context.txt` — API docs, a policy PDF converted to text, a product spec, etc.

**Different questions:** edit the `QUESTIONS` list. More questions = more pronounced savings curve.

**Different providers:** add a Run D by calling `run_session()` with a different `provider_order`, e.g. `["Google Vertex"]`.

---

Built by [context-window-ai](https://github.com/context-window-ai).
