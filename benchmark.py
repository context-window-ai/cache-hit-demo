"""
Cache Hit Benchmark — context-window-ai
Measures cost, latency, and cache hit rate across three routing configurations
using OpenRouter + Claude Sonnet 4.6, with full Langfuse observability.

Usage:
    1. Run scripts/generate_context.sh to build codebase_context.txt
    2. Copy .env.example to .env and fill in your keys
    3. python benchmark.py
"""

import os
import time
import json
from dotenv import load_dotenv

# Langfuse drop-in OpenAI wrapper — traces every completion automatically
from langfuse.openai import openai

load_dotenv()

# ── Env var validation ────────────────────────────────────────────────────────

REQUIRED_VARS = [
    "OPENROUTER_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}\n"
        "Copy .env.example to .env and fill in your keys."
    )

# ── Client ────────────────────────────────────────────────────────────────────

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    default_headers={
        # OpenRouter ranks apps by these headers — good practice to set them
        "HTTP-Referer": "https://github.com/context-window-ai/cache-hit-demo",
        "X-Title": "Cache Hit Benchmark",
    },
)

# ── Config ────────────────────────────────────────────────────────────────────

MODEL = "anthropic/claude-sonnet-4-6"
CONTEXT_FILE = "codebase_context.txt"

QUESTIONS = [
    "How does authentication work in this SDK?",
    "Where are HTTP retries handled and what's the backoff strategy?",
    "What streaming response types are supported and how are they parsed?",
    "How would I add request-level timeout overrides?",
    "Find all places where error handling could be improved.",
    "How does the SDK handle provider fallbacks?",
    "What does the usage object look like in a response?",
    "How would I add a middleware layer to log every request?",
    "Where is rate limiting logic implemented, if anywhere?",
    "How would I extend this SDK to support a new provider?",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_codebase() -> str:
    if not os.path.exists(CONTEXT_FILE):
        raise FileNotFoundError(
            f"{CONTEXT_FILE} not found.\n"
            "Run:  bash scripts/generate_context.sh"
        )
    with open(CONTEXT_FILE) as f:
        content = f.read()
    print(f"Loaded codebase: {len(content):,} chars")
    return content


def run_session(
    label: str,
    use_cache: bool,
    codebase: str,
    provider_order: list[str] | None = None,
) -> list[dict]:
    """Run all QUESTIONS against the model and record per-turn metrics."""
    print(f"\n{'═' * 62}")
    print(f"  {label}")
    print(f"{'═' * 62}")

    # Slug used for Langfuse session grouping
    run_slug = label.lower()
    for ch in " ,()—":
        run_slug = run_slug.replace(ch, "-")
    run_slug = run_slug.strip("-")

    # Build system message — optionally with cache_control breakpoint
    # cache_control tells Anthropic (via OpenRouter) to cache this content block.
    # Turn 1 always misses (cold); subsequent turns hit the warm cache.
    # NOTE: Verify this is working by checking cached_tokens > 0 on Turn 2+.
    system_content = [
        {
            "type": "text",
            "text": (
                "You are a code review assistant. "
                "Here is the full codebase:\n\n"
                + codebase
            ),
        }
    ]
    if use_cache:
        system_content[0]["cache_control"] = {"type": "ephemeral"}

    # Provider routing
    extra_body: dict = {}
    if provider_order:
        extra_body["provider"] = {
            "order": provider_order,
            "allow_fallbacks": False,
        }

    results = []

    for i, question in enumerate(QUESTIONS):
        turn_num = i + 1
        start = time.time()

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": question},
            ],
            extra_body=extra_body,
            max_tokens=300,
            # ── Langfuse metadata ──────────────────────────────────────────
            # These fields are intercepted by langfuse.openai and NOT forwarded
            # to OpenRouter. They appear in your Langfuse dashboard.
            name=f"cache-benchmark-turn-{turn_num:02d}",
            session_id=f"benchmark-{run_slug}",
            metadata={
                "run_label": label,
                "use_cache": use_cache,
                "turn": turn_num,
                "question": question,
                "provider_order": provider_order or "default",
            },
            tags=[
                "cache-benchmark",
                "openrouter",
                "cache-on" if use_cache else "cache-off",
            ],
        )

        latency = time.time() - start
        usage = response.usage

        # cached_tokens lives inside prompt_tokens_details (OpenAI SDK >= 1.40)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(prompt_details, "cached_tokens", 0) or 0
        cost = getattr(usage, "cost", None) or 0.0
        hit_rate = round(cached / usage.prompt_tokens, 3) if usage.prompt_tokens else 0

        results.append(
            {
                "turn": turn_num,
                "question": question[:50],
                "prompt_tokens": usage.prompt_tokens,
                "cached_tokens": cached,
                "completion_tokens": usage.completion_tokens,
                "cache_hit_rate": hit_rate,
                "cost_usd": cost,
                "latency_s": round(latency, 2),
            }
        )

        indicator = "🟢" if cached > 0 else "⚪"
        print(
            f"  {indicator} Turn {turn_num:2d}: "
            f"cached={cached:>6,} / {usage.prompt_tokens:>6,} tokens "
            f"({hit_rate * 100:>4.0f}% hit) | "
            f"${cost:.5f} | {latency:.1f}s"
        )

    total_cost = sum(r["cost_usd"] for r in results)
    avg_latency = sum(r["latency_s"] for r in results) / len(results)
    avg_hit = sum(r["cache_hit_rate"] for r in results) / len(results)

    print(f"  {'─' * 56}")
    print(f"  TOTAL COST:     ${total_cost:.4f}")
    print(f"  AVG LATENCY:    {avg_latency:.1f}s")
    print(f"  AVG CACHE HIT:  {avg_hit * 100:.0f}%")

    return results


def print_summary(runs: dict[str, list[dict]]) -> None:
    print(f"\n{'═' * 62}")
    print("  BENCHMARK SUMMARY")
    print(f"{'═' * 62}")
    header = f"{'Run':<38} {'Total Cost':>10} {'Avg Lat':>9} {'Avg Hit':>9}"
    print(header)
    print("─" * len(header))
    for label, results in runs.items():
        total_cost = sum(r["cost_usd"] for r in results)
        avg_latency = sum(r["latency_s"] for r in results) / len(results)
        avg_hit = sum(r["cache_hit_rate"] for r in results) / len(results)
        print(
            f"  {label:<36} ${total_cost:>8.4f} {avg_latency:>8.1f}s {avg_hit * 100:>8.0f}%"
        )

    # Cost savings vs Run A
    costs = [sum(r["cost_usd"] for r in v) for v in runs.values()]
    if costs[0] > 0:
        print()
        labels = list(runs.keys())
        for i in range(1, len(costs)):
            savings = (1 - costs[i] / costs[0]) * 100
            print(f"  💰 {labels[i]} saves {savings:.0f}% vs {labels[0]}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    codebase = load_codebase()

    run_A = run_session(
        label="A — No Cache (Anthropic)",
        use_cache=False,
        codebase=codebase,
        provider_order=["Anthropic"],
    )

    run_B = run_session(
        label="B — Cache ON, Anthropic",
        use_cache=True,
        codebase=codebase,
        provider_order=["Anthropic"],
    )

    run_C = run_session(
        label="C — Cache ON, Bedrock",
        use_cache=True,
        codebase=codebase,
        provider_order=["Amazon Bedrock"],
    )

    runs = {
        "A — No Cache (Anthropic)": run_A,
        "B — Cache ON, Anthropic": run_B,
        "C — Cache ON, Bedrock": run_C,
    }

    print_summary(runs)

    # ── Save results ──────────────────────────────────────────────────────────
    os.makedirs("results", exist_ok=True)
    output_path = "results/cache_benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "A": run_A,
                "B": run_B,
                "C": run_C,
                "meta": {
                    "model": MODEL,
                    "num_questions": len(QUESTIONS),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            },
            f,
            indent=2,
        )
    print(f"Results saved → {output_path}")

    # ── Flush Langfuse ────────────────────────────────────────────────────────
    # Ensures all trace data is shipped before the process exits.
    print("Flushing Langfuse traces...")
    from langfuse import Langfuse

    Langfuse().flush()
    print("✅ Done — check cloud.langfuse.com for your traces.")
    print(f"   Filter by tag: cache-benchmark")


if __name__ == "__main__":
    main()
