export type HarnessId = 'codex' | 'claude-code' | 'cursor' | 'antigravity' | 'opencode' | 'hermes';
export type ProviderMode = 'gateway' | 'openrouter' | 'vllm' | 'subscription' | 'manual';
export type AuthMode = 'account-plan' | 'provider-api-key' | 'oauth' | 'self-hosted-endpoint' | 'provider-specific';

export type HarnessCatalogEntry = {
  id: HarnessId;
  name: string;
  kind: 'cli' | 'ide' | 'agent-runtime';
  description: string;
  authModes: AuthMode[];
  providers: ProviderMode[];
  billingNotes: string[];
  sources: { label: string; url: string; checkedAt: string }[];
};

const checkedAt = '2026-09-27';

/** Product/auth catalog only. It makes no claim that a logged-in plan grants API access. */
export const harnessCatalog: readonly HarnessCatalogEntry[] = [
  {
    id: 'codex',
    name: 'Codex',
    kind: 'cli',
    description: 'OpenAI coding agent available through the Codex app, CLI, and editor integrations.',
    authModes: ['account-plan', 'provider-api-key'],
    providers: ['subscription', 'gateway', 'manual'],
    billingNotes: [
      'ChatGPT sign-in uses the eligible plan allowance or credits shown for that account/workspace; this is not a per-token invoice estimate.',
      'OpenAI API-key usage is separate metered API billing. Enterprise billing may use credits or token-based rates depending on the workspace.',
    ],
    sources: [
      { label: 'Using Codex with your ChatGPT plan', url: 'https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan', checkedAt },
      { label: 'Codex CLI and Sign in with ChatGPT', url: 'https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt', checkedAt },
    ],
  },
  {
    id: 'claude-code',
    name: 'Claude Code',
    kind: 'cli',
    description: 'Anthropic coding agent for terminal workflows, with account-plan and API/cloud authentication paths.',
    authModes: ['account-plan', 'provider-api-key', 'provider-specific'],
    providers: ['subscription', 'gateway', 'manual'],
    billingNotes: [
      'Claude Pro/Max plans include Claude Code access subject to plan limits; Anthropic Console API usage is billed separately.',
      'Bedrock, Vertex AI, and other compatible gateways follow their own billing and credential terms.',
    ],
    sources: [
      { label: 'Claude Code setup and authentication', url: 'https://docs.anthropic.com/en/docs/claude-code/getting-started', checkedAt },
      { label: 'Claude plan and API billing separation', url: 'https://support.anthropic.com/en/articles/9876003-i-subscribe-to-a-paid-claude-ai-plan-why-do-i-have-to-pay-separately-for-api-usage-on-console', checkedAt },
    ],
  },
  {
    id: 'cursor',
    name: 'Cursor',
    kind: 'ide',
    description: 'AI code editor and agents with product usage pools, BYOK for supported chat models, and SDK/CLI options.',
    authModes: ['account-plan', 'provider-api-key'],
    providers: ['subscription', 'manual'],
    billingNotes: [
      'Cursor plan usage pools and usage-based charges are product-specific; do not price them as a generic subscription entitlement.',
      'BYOK model charges are paid to the configured model provider. Cursor documents a separate token-rate allowance for Teams/Enterprise BYOK; it is not always an extra cash charge.',
      'Cursor custom keys apply to supported chat models, not every feature. Background agents have separate model and compute billing behavior.',
    ],
    sources: [
      { label: 'Cursor models and pricing', url: 'https://cursor.com/docs/models-and-pricing', checkedAt },
      { label: 'Cursor BYOK and usage details', url: 'https://prod.cursor.com/help/models-and-usage/api-keys', checkedAt },
      { label: 'Cursor pricing', url: 'https://cursor.com/pricing', checkedAt },
    ],
  },
  {
    id: 'antigravity',
    name: 'Google Antigravity',
    kind: 'ide',
    description: 'Google agentic development environment, with individual plans and an API-hosted Antigravity agent path.',
    authModes: ['account-plan', 'provider-api-key', 'provider-specific'],
    providers: ['subscription', 'manual'],
    billingNotes: [
      'Individual Antigravity plans provide rate-limited product usage; Google AI plan access and quotas are not a token invoice.',
      'The Antigravity agent available through Gemini API/Interactions is billed from underlying token use and tool calls. Treat that as an API path, separate from an IDE subscription.',
      'Organization use through Gemini Enterprise Agent Platform follows Google Cloud consumption pricing.',
    ],
    sources: [
      { label: 'Antigravity pricing and plan availability', url: 'https://antigravity.google/pricing', checkedAt },
      { label: 'Antigravity agent API availability and pricing', url: 'https://ai.google.dev/gemini-api/docs/antigravity-agent', checkedAt },
      { label: 'Gemini API billing', url: 'https://ai.google.dev/gemini-api/docs/billing', checkedAt },
    ],
  },
  {
    id: 'opencode',
    name: 'OpenCode',
    kind: 'cli',
    description: 'Open-source coding agent with broad provider support and local model endpoints.',
    authModes: ['provider-api-key', 'oauth', 'self-hosted-endpoint'],
    providers: ['gateway', 'openrouter', 'vllm', 'manual', 'subscription'],
    billingNotes: [
      'OpenCode connects to provider credentials; the selected provider/model determines the metered cost.',
      'Subscription-style access may be provided by a provider integration or add-on. This catalog does not infer subscription/API entitlement from a plan name.',
      'Local model hosting has compute and power costs that must be entered separately.',
    ],
    sources: [
      { label: 'OpenCode provider setup', url: 'https://opencode.ai/docs/providers', checkedAt },
    ],
  },
  {
    id: 'hermes',
    name: 'Hermes Agent',
    kind: 'agent-runtime',
    description: 'Nous Research agent runtime that supports API providers, OAuth-backed providers, subscription gateways, and local endpoints.',
    authModes: ['provider-api-key', 'oauth', 'account-plan', 'self-hosted-endpoint', 'provider-specific'],
    providers: ['gateway', 'openrouter', 'vllm', 'subscription', 'manual'],
    billingNotes: [
      'A provider connection can be metered API access, a provider-managed subscription/OAuth path, or a local endpoint; these billing contracts are distinct.',
      'Nous Portal and other OAuth products have their own entitlements and limits. They are not equivalent to OpenRouter or direct API pricing.',
      'Hermes also supports custom OpenAI-compatible endpoints such as vLLM; enter hosting costs explicitly.',
    ],
    sources: [
      { label: 'Hermes provider quickstart', url: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/getting-started/quickstart.md', checkedAt },
      { label: 'Hermes supported providers', url: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md', checkedAt },
      { label: 'Hermes provider and authentication FAQ', url: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/faq.md', checkedAt },
    ],
  },
];

export function getHarness(id: HarnessId): HarnessCatalogEntry {
  const harness = harnessCatalog.find(item => item.id === id);
  if (!harness) throw new Error(`Unknown harness: ${id}`);
  return harness;
}
