"""
generate_blog.py — context-window-ai/cache-hit-demo

Reads results/cache_benchmark_results.json and renders a full markdown
blog post draft with real numbers, ready to paste into Dev.to, Hashnode,
Ghost, or any other platform.

Usage:
    python generate_blog.py
    python generate_blog.py --results path/to/results.json --out my_post.md
"""

import argparse
import json
import os
import sys
from datetime import datetime

RESULTS_PATH = "results/cache_benchmark_results.json"
OUTPUT_PATH = "results/blog_post_draft.md"
CHART_PATH = "results/benchmark_chart.png"
REPO_URL = "https://github.com/context-window-ai/cache-hit-demo"


def load_results(path: str) -> dict:
    if not os.path.exists(path):
        print(f"❌  Results file not found: {path}")
        print("    Run benchmark.py first, then visualize.py to generate the chart.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def summarise(results: list[dict]) -> dict:
    total_cost = sum(r["cost_usd"] for r in results)
    avg_latency = sum(r["latency_s"] for r in results) / len(results)
    avg_hit = sum(r["cache_hit_rate"] for r in results) / len(results)
    # Turn 1 always misses — avg hit from turn 2 onward is the "steady state"
    steady_hit = (
        sum(r["cache_hit_rate"] for r in results[1:]) / len(results[1:])
        if len(results) > 1
        else 0
    )
    peak_hit = max(r["cache_hit_rate"] for r in results)
    return {
        "total_cost": total_cost,
        "avg_latency": avg_latency,
        "avg_hit": avg_hit,
        "steady_hit": steady_hit,
        "peak_hit": peak_hit,
        "turn1_latency": results[0]["latency_s"],
        "turn2_latency": results[1]["latency_s"] if len(results) > 1 else None,
        "turn1_cost": results[0]["cost_usd"],
        "turn2_cost": results[1]["cost_usd"] if len(results) > 1 else None,
    }


def render(data: dict) -> str:
    A = summarise(data["A"])
    B = summarise(data["B"])
    C = summarise(data["C"])
    meta = data.get("meta", {})
    model = meta.get("model", "anthropic/claude-sonnet-4-6")
    n = meta.get("num_questions", 10)
    ts = meta.get("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    date_str = ts[:10]

    savings_B = (1 - B["total_cost"] / A["total_cost"]) * 100 if A["total_cost"] else 0
    savings_C = (1 - C["total_cost"] / A["total_cost"]) * 100 if A["total_cost"] else 0
    latency_improvement_B = (1 - B["avg_latency"] / A["avg_latency"]) * 100 if A["avg_latency"] else 0

    post = f"""\
---
title: "Prompt Caching with OpenRouter: A Real-World Cost & Latency Benchmark"
date: {date_str}
tags: [AI, LLMs, OpenRouter, Anthropic, Langfuse, PromptCaching]
canonical_url: {REPO_URL}
---

# Prompt Caching with OpenRouter: A Real-World Cost & Latency Benchmark

When you're running the same large context repeatedly — a system prompt stuffed with documentation, a codebase, a long policy document — you're paying to re-encode it on every single call. Anthropic's prompt caching lets you store that context server-side and reference it cheaply on subsequent turns. The question is: how much does it actually matter in practice?

We ran a controlled benchmark to find out. Same model (`{model}`), same 10 questions, three routing configurations through [OpenRouter](https://openrouter.ai), with every call traced in [Langfuse](https://langfuse.com) for observability. All the code is open source: [{REPO_URL}]({REPO_URL}).

---

## The Setup

We cloned the [OpenRouter Python SDK](https://github.com/OpenRouterTeam/openrouter-python), concatenated all its source files into a single context string, and asked {n} code review questions against it — the kind of thing you'd do when building a Q&A tool over a codebase.

Three runs, differentiated only by routing and caching settings:

| Run | Config | Cache? |
|-----|--------|--------|
| **A** | Anthropic (direct) | ❌ No |
| **B** | Anthropic (direct) | ✅ Yes — ephemeral breakpoint |
| **C** | Amazon Bedrock | ✅ Yes — ephemeral breakpoint |

The caching mechanism is Anthropic's `cache_control` breakpoint, which marks a content block for server-side storage. The first call is always a cache miss (the context has to be written). Every subsequent call within the TTL window is a hit.

```python
system_content = [{{
    "type": "text",
    "text": f"You are a code review assistant. Here is the codebase:\\n\\n{{codebase}}",
    "cache_control": {{"type": "ephemeral"}}   # mark this block for caching
}}]
```

---

## Results

![Benchmark chart showing cost, latency, and cache hit rate across three runs](benchmark_chart.png)

### Cost

| Run | Total ({n} questions) | vs. No Cache |
|-----|-----------------------|-------------|
| A — No Cache | ${A["total_cost"]:.4f} | baseline |
| B — Cache ON, Anthropic | ${B["total_cost"]:.4f} | **{savings_B:.0f}% cheaper** |
| C — Cache ON, Bedrock | ${C["total_cost"]:.4f} | **{savings_C:.0f}% cheaper** |

Turn 1 always incurs the full cost — that's the cache write. But from Turn 2 onward, the savings are immediate: Run B's second question cost ${B["turn2_cost"]:.5f} versus ${A["turn2_cost"]:.5f} for Run A with no caching.

### Latency

| Run | Avg Latency | Turn 1 | Turn 2+ |
|-----|-------------|--------|---------|
| A — No Cache | {A["avg_latency"]:.1f}s | {A["turn1_latency"]:.1f}s | ~{A["avg_latency"]:.1f}s |
| B — Cache ON | {B["avg_latency"]:.1f}s | {B["turn1_latency"]:.1f}s | ~{B["turn2_latency"]:.1f}s |
| C — Cache ON (Bedrock) | {C["avg_latency"]:.1f}s | {C["turn1_latency"]:.1f}s | ~{C["turn2_latency"]:.1f}s |

Cached runs were roughly **{latency_improvement_B:.0f}% faster** on average versus no caching. This makes sense: the model skips re-encoding the large context block and goes straight to the generation step.

### Cache Hit Rate

Run B achieved a steady-state cache hit rate of **{B["steady_hit"]*100:.0f}%** from Turn 2 onward (peak: {B["peak_hit"]*100:.0f}%). Run C on Bedrock hit **{C["steady_hit"]*100:.0f}%** steady-state. The Turn 1 miss is expected and unavoidable — that's the price of warming the cache.

---

## Observability with Langfuse

Every call is traced automatically via the [Langfuse OpenAI drop-in wrapper](https://langfuse.com/docs/integrations/openai):

```python
from langfuse.openai import openai   # replaces: import openai

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
```

From there, each `chat.completions.create()` call accepts Langfuse metadata fields that show up in your dashboard:

```python
response = client.chat.completions.create(
    model="{model}",
    messages=[...],
    name="cache-benchmark-turn-02",
    session_id="benchmark-run-b",
    metadata={{"run_label": "B", "use_cache": True, "turn": 2}},
    tags=["cache-benchmark", "cache-on"],
)
```

In the Langfuse dashboard you can filter by tag (`cache-benchmark`), group by session to compare runs A/B/C side-by-side, and see per-call token usage and cost — including whether `cached_tokens` is populated.

This is particularly useful for validating that `cache_control` is actually working: if `cached_tokens` is 0 on Turn 2+, the breakpoint isn't being honoured and you're paying full price.

---

## Key Takeaways

**Cache early, cache aggressively.** If your system prompt or context is larger than ~1,000 tokens and you're making repeated calls, caching is essentially free money. The write cost on Turn 1 is the same as a normal call; every subsequent turn is dramatically cheaper and faster.

**The breakpoint placement matters.** We put `cache_control` on the codebase block in the system message. If you're building a multi-turn chat application, you'd want to put it at the end of a long document or tool definition — not mid-conversation where the cache would be invalidated on every turn.

**Bedrock vs. Anthropic direct are close.** Both providers support Anthropic's prompt caching and both showed similar hit rates in our benchmark. The small latency difference is likely infrastructure routing, not caching behaviour.

**Observability isn't optional.** Without Langfuse, you'd be flying blind on whether caching is actually kicking in. The `cached_tokens` field in the usage object is your ground truth — make sure something is logging it.

---

## Run It Yourself

```bash
git clone {REPO_URL}
cd cache-hit-demo
cp .env.example .env      # add your OpenRouter + Langfuse keys
pip install -r requirements.txt
bash scripts/generate_context.sh
python benchmark.py
python visualize.py
python generate_blog.py   # generates this post from your real numbers
```

The full benchmark takes around {int(n * A["avg_latency"] * 3 / 60) + 1}–{int(n * A["avg_latency"] * 3 / 60) + 3} minutes to run all three sessions. Results are saved to `results/` for inspection and charting.

---

*Built by [context-window-ai]({REPO_URL.rsplit("/", 1)[0]}). Questions or PRs welcome.*
"""
    return post


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate blog post from benchmark results")
    parser.add_argument("--results", default=RESULTS_PATH)
    parser.add_argument("--out", default=OUTPUT_PATH)
    args = parser.parse_args()

    data = load_results(args.results)
    post = render(data)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(post)

    print(f"✅  Blog post draft saved → {args.out}")
    print("    Review and fill in any [BRACKETS] before publishing.")


if __name__ == "__main__":
    main()
