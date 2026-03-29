---
title: "Prompt Caching with OpenRouter: A Real-World Cost & Latency Benchmark"
date: 2026-03-28
tags: [AI, LLMs, OpenRouter, Anthropic, PromptCaching]
canonical_url: https://github.com/context-window-ai/cache-hit-demo
---

# Prompt Caching with OpenRouter: A Real-World Cost & Latency Benchmark

When you're running the same large context repeatedly — a system prompt stuffed with documentation, a codebase, a long policy document — you're paying to re-encode it on every single call. Anthropic's prompt caching lets you store that context server-side and reference it cheaply on subsequent turns. The question is: how much does it actually matter in practice?

We ran a controlled benchmark to find out. Same model (`anthropic/claude-sonnet-4-6`), same 10 questions, three routing configurations through [OpenRouter](https://openrouter.ai). All the code is open source: [https://github.com/context-window-ai/cache-hit-demo](https://github.com/context-window-ai/cache-hit-demo).

---

## The Setup

We cloned the [OpenRouter Python SDK](https://github.com/OpenRouterTeam/openrouter-python), concatenated all its source files into a single context string, and asked 10 code review questions against it — the kind of thing you'd do when building a Q&A tool over a codebase.

Three runs, differentiated only by routing and caching settings:

| Run | Config | Cache? |
|-----|--------|--------|
| **A** | Anthropic (direct) | ❌ No |
| **B** | Anthropic (direct) | ✅ Yes — ephemeral breakpoint |
| **C** | Amazon Bedrock | ✅ Yes — ephemeral breakpoint |

The caching mechanism is Anthropic's `cache_control` breakpoint, which marks a content block for server-side storage. The first call is always a cache miss (the context has to be written). Every subsequent call within the TTL window is a hit.

```python
system_content = [{
    "type": "text",
    "text": f"You are a code review assistant. Here is the codebase:\n\n{codebase}",
    "cache_control": {"type": "ephemeral"}   # mark this block for caching
}]
```

---

## Results

![Benchmark chart showing cost, latency, and cache hit rate across three runs](benchmark_chart.png)

### Cost

| Run | Total (10 questions) | vs. No Cache |
|-----|-----------------------|-------------|
| A — No Cache | $16.3856 | baseline |
| B — Cache ON, Anthropic | $3.5586 | **78% cheaper** |
| C — Cache ON, Bedrock | $3.5586 | **78% cheaper** |

Turn 1 always incurs the full cost — that's the cache write. But from Turn 2 onward, the savings are immediate: Run B's second question cost $0.16796 versus $1.63857 for Run A with no caching.

### Latency

| Run | Avg Latency | Turn 1 | Turn 2+ |
|-----|-------------|--------|---------|
| A — No Cache | 10.8s | 20.3s | ~10.8s |
| B — Cache ON | 9.7s | 8.3s | ~9.4s |
| C — Cache ON (Bedrock) | 9.9s | 17.6s | ~8.4s |

Cached runs were roughly **10% faster** on average versus no caching. This makes sense: the model skips re-encoding the large context block and goes straight to the generation step.

### Cache Hit Rate

Run B achieved a steady-state cache hit rate of **100%** from Turn 2 onward (peak: 100%). Run C on Bedrock hit **100%** steady-state. The Turn 1 miss is expected and unavoidable — that's the price of warming the cache.

---

## Observability

Every request lands automatically in your [OpenRouter activity log](https://openrouter.ai/workspaces/default/observability) — no extra setup needed. You can see `cached_tokens`, cost, and latency per call and filter by model or API key.

This is the most direct way to validate that caching is actually working: if `cached_tokens` is 0 on Turn 2+ of runs B and C, the `cache_control` breakpoint isn't being honoured and you're paying full price.

If you want to forward traces to Langfuse, Grafana, Datadog, or Braintrust, OpenRouter's **Broadcast** feature handles that at the infrastructure level — no code changes required. Enable it in your workspace settings and every request is mirrored to whichever backends you configure.

---

## Key Takeaways

**Cache early, cache aggressively.** If your system prompt or context is larger than ~1,000 tokens and you're making repeated calls, caching is essentially free money. The write cost on Turn 1 is the same as a normal call; every subsequent turn is dramatically cheaper and faster.

**The breakpoint placement matters.** We put `cache_control` on the codebase block in the system message. If you're building a multi-turn chat application, you'd want to put it at the end of a long document or tool definition — not mid-conversation where the cache would be invalidated on every turn.

**Bedrock vs. Anthropic direct are close.** Both providers support Anthropic's prompt caching and both showed similar hit rates in our benchmark. The small latency difference is likely infrastructure routing, not caching behaviour.

**Observability isn't optional.** The `cached_tokens` field in the usage object is your ground truth — OpenRouter logs it per request automatically. If it's 0 on Turn 2+, something is wrong and you're paying full price without realising it.

---

## Run It Yourself

```bash
git clone https://github.com/context-window-ai/cache-hit-demo
cd cache-hit-demo
cp .env.example .env      # add your OPENROUTER_API_KEY
pip install -r requirements.txt
bash scripts/generate_context.sh
python benchmark.py
python visualize.py
python generate_blog.py   # generates this post from your real numbers
```

The full benchmark takes around 6–8 minutes to run all three sessions. Results are saved to `results/` for inspection and charting.

---

*Built by [context-window-ai](https://github.com/context-window-ai). Questions or PRs welcome.*
