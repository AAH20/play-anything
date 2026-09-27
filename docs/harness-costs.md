# Harness and execution cost estimates

The web workspace separates the coding harness from the billing path. The catalog recognizes Codex, Claude Code, Cursor, Google Antigravity, OpenCode, and Hermes Agent. The selected harness describes where an agent is run; the billing provider describes how its model usage or compute is charged. Selecting one never configures credentials, launches a provider, or proves a plan includes programmatic/API access.

## Billing distinctions

| Harness | Documented authentication/billing distinction | Primary sources |
| --- | --- | --- |
| Codex | Sign-in with ChatGPT consumes eligible plan allowances/credits; OpenAI API-key requests are separate metered billing. Enterprise arrangements can vary. | [Codex on ChatGPT plans](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan), [Codex CLI sign-in and API](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt) |
| Claude Code | Claude Pro/Max access is subscription usage subject to plan limits; Anthropic Console API usage is billed separately. Cloud providers have their own rates and credentials. | [Claude Code setup](https://docs.anthropic.com/en/docs/claude-code/getting-started), [Claude plan vs API billing](https://support.anthropic.com/en/articles/9876003-i-subscribe-to-a-paid-claude-ai-plan-why-do-i-have-to-pay-separately-for-api-usage-on-console) |
| Cursor | Product usage pools and usage-based charges are plan-specific. BYOK is available for supported chat models; the model provider generally bills its requests, with distinct Cursor token-rate treatment on some Teams/Enterprise plans. | [Cursor models and pricing](https://cursor.com/docs/models-and-pricing), [Cursor BYOK](https://prod.cursor.com/help/models-and-usage/api-keys), [Cursor pricing](https://cursor.com/pricing) |
| Google Antigravity | IDE/plan access has product quotas. The separate Antigravity agent API is billed from underlying Gemini token and tool use; enterprise use can follow Google Cloud consumption pricing. | [Antigravity pricing](https://antigravity.google/pricing), [Antigravity Agent API](https://ai.google.dev/gemini-api/docs/antigravity-agent), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing) |
| OpenCode | Connects to provider accounts, API keys, and local endpoints. Provider integrations determine subscription access and billing; the harness itself does not imply free inference. | [OpenCode providers](https://opencode.ai/docs/providers) |
| Hermes Agent | Supports direct APIs, OAuth/subscription integrations, and local endpoints. Entitlements and usage are provider-specific. | [Hermes quickstart](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/getting-started/quickstart.md), [providers](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md), [FAQ](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md) |

Plan allowances, account quotas, provider promotions, and product prices change. These links were checked on 2026-09-27. Confirm the active account, region, plan, and provider terms before using a budget for purchasing decisions. In particular, do not treat a subscription as unlimited programmatic access or as zero marginal cost: enter the attributable fixed subscription allocation, then separately measure any quota use or overages.

## Token rate references

The UI includes an editable snapshot of the public [OpenRouter model catalog](https://openrouter.ai/api/v1/models), checked 2026-09-27. The rates below are USD per 1 million tokens; blank or absent fields remain unknown in the calculation.

| Model ID | Input | Output | Cache read | Cache write | Snapshot caveat |
| --- | ---: | ---: | ---: | ---: | --- |
| `openai/gpt-5.6-sol` | $1.00 | $6.00 | $0.10 | Unknown | Catalog describes a higher input/output tier beyond 272k prompt tokens; not modeled. |
| `anthropic/claude-opus-4.6` | $5.00 | $25.00 | $0.50 | $6.25 | One blended rate; provider-specific prompt tiers/discounts are not modeled. |
| `qwen/qwen3.6-35b-a3b` | $0.15 | $1.00 | $0.05 | Unknown | Cache-write rate was absent in the retrieved entry. |

The OpenRouter snapshot selects only a cost reference. The runtime's configured model may differ; the UI states this explicitly. Edit rates to match the actual execution model and current provider account. A missing rate with nonzero tokens makes dependent totals unknown; it is never silently treated as free.

## Self-hosted vLLM

For vLLM, the calculator records model token inference as $0 of external API metering and separately estimates GPU hosting from entered GPU-hours, hourly price, and utilization. A public reference shown in the UI is RunPod Secure H100 SXM at **$3.49 per GPU-hour**, checked 2026-09-13 ([RunPod pricing](https://www.runpod.io/pricing)). Enter the actual instance/region quote instead. That reference does not include storage, networking, power outside the instance price, engineering/operations time, taxes, or reserved-capacity terms. vLLM exposes an OpenAI-compatible server and supports GPU deployments; hardware and installation requirements are documented in the [vLLM GPU installation guide](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/).

## Calculator model

Per-started-run model cost is the sum of input, output, cache-read, and cache-write token charges per agent attempt, multiplied by `agents × (1 + retries per agent)`. Cache-read tokens are separate from uncached input tokens; avoid double-counting them. vLLM replaces API token charges with GPU hosting. Manual mode can include token rates and, when supplied, a GPU component.

GPU cost per started run is `GPU-hour rate × GPU count × wall-clock hours per agent attempt × attempts ÷ utilization fraction`. Lower utilization spreads the allocated GPU hourly charge over fewer useful workloads, increasing cost per run. For dedicated/reserved instances, also enter reserved monthly GPU cost if that charge is not already represented by the per-run hours.

The calculator allocates `subscription price × allocation percentage` plus other monthly fixed cost across planned started runs. Monthly spend is that fixed allocation plus modeled variable spend. Cost per successful run divides monthly spend by expected successful runs (`planned runs × success rate`). Expected revenue and contribution use revenue per successful run; break-even runs solve the fixed allocation against contribution per started run. A zero success rate, nonpositive contribution, or unknown input leaves break-even unknown. Budgets are checked against estimated all-in cost per run and monthly spend.

Retries, fanout, and low success rates can dominate unit economics. Use measured token/latency/attempt data from the actual workload; the initial UI token counts are illustrative inputs, not benchmark claims. Include cache writes, provider-specific long-context tiers, batch discounts, tools, storage, egress, and human review only when their cost treatment is known. Estimates are planning aids, not invoices or accounting records.
