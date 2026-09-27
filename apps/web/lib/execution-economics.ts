import { type HarnessId, type ProviderMode } from './harness-catalog';

export const OPENROUTER_RATES_CHECKED_AT = '2026-09-27';
export const OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models';
export const RUNPOD_RATES_CHECKED_AT = '2026-09-13';
export const RUNPOD_PRICING_URL = 'https://www.runpod.io/pricing';

export type TokenRates = {
  inputPerMillionUsd: number | null;
  outputPerMillionUsd: number | null;
  cacheReadPerMillionUsd: number | null;
  cacheWritePerMillionUsd: number | null;
};

export type RateCard = {
  id: string;
  label: string;
  modelId: string;
  provider: 'openrouter';
  rates: TokenRates;
  checkedAt: string;
  sourceUrl: string;
  note?: string;
};

/** OpenRouter API metadata snapshot, USD per 1M tokens, retrieved 2026-09-27. */
export const OPENROUTER_RATE_CARDS: readonly RateCard[] = [
  {
    id: 'or-gpt-5.6-sol',
    label: 'OpenAI GPT-5.6 Sol · OpenRouter',
    modelId: 'openai/gpt-5.6-sol',
    provider: 'openrouter',
    rates: { inputPerMillionUsd: 1, outputPerMillionUsd: 6, cacheReadPerMillionUsd: 0.1, cacheWritePerMillionUsd: null },
    checkedAt: OPENROUTER_RATES_CHECKED_AT,
    sourceUrl: OPENROUTER_MODELS_URL,
    note: 'OpenRouter metadata also has a higher prompt price beyond its 272k-token threshold; this simple calculator does not model that tier. Cache-write price was absent in the returned catalog entry.',
  },
  {
    id: 'or-claude-opus-4.6',
    label: 'Anthropic Claude Opus 4.6 · OpenRouter',
    modelId: 'anthropic/claude-opus-4.6',
    provider: 'openrouter',
    rates: { inputPerMillionUsd: 5, outputPerMillionUsd: 25, cacheReadPerMillionUsd: 0.5, cacheWritePerMillionUsd: 6.25 },
    checkedAt: OPENROUTER_RATES_CHECKED_AT,
    sourceUrl: OPENROUTER_MODELS_URL,
  },
  {
    id: 'or-qwen3.6-35b',
    label: 'Qwen3.6 35B A3B · OpenRouter',
    modelId: 'qwen/qwen3.6-35b-a3b',
    provider: 'openrouter',
    rates: { inputPerMillionUsd: 0.15, outputPerMillionUsd: 1, cacheReadPerMillionUsd: 0.05, cacheWritePerMillionUsd: null },
    checkedAt: OPENROUTER_RATES_CHECKED_AT,
    sourceUrl: OPENROUTER_MODELS_URL,
    note: 'Cache-write price was absent in the returned catalog entry.',
  },
];

export type EconomicsInput = {
  harnessId: HarnessId;
  provider: ProviderMode;
  workloadKind?: 'kernel' | 'model' | 'framework' | 'harness';
  kernelComputeCostPerStartedRunUsd?: number | null;
  rates: TokenRates;
  uncachedInputTokensPerAgentAttempt: number;
  outputTokensPerAgentAttempt: number;
  cacheReadTokensPerAgentAttempt: number;
  cacheWriteTokensPerAgentAttempt: number;
  agentsPerRun: number;
  retriesPerAgent: number;
  successRatePercent: number;
  plannedRunsPerMonth: number;
  allocatedSubscriptionMonthlyUsd: number;
  subscriptionAllocationPercent: number;
  otherFixedMonthlyUsd: number;
  reservedGpuMonthlyUsd: number;
  gpuRateUsdPerGpuHour: number | null;
  gpuCount: number;
  gpuWallClockHoursPerAgentAttempt: number | null;
  gpuUtilizationPercent: number | null;
  revenuePerSuccessfulRunUsd: number | null;
  perRunBudgetUsd: number | null;
  monthlyBudgetUsd: number | null;
};

export type BudgetStatus = 'not-set' | 'within' | 'exceeds' | 'unknown';

export type ExecutionEstimate = {
  currency: 'USD';
  harnessId: HarnessId;
  provider: ProviderMode;
  workloadKind?: 'kernel' | 'model' | 'framework' | 'harness';
  attemptsPerRun: number;
  expectedSuccessfulRunsPerMonth: number;
  allocatedSubscriptionMonthlyUsd: number;
  allocatedFixedMonthlyUsd: number;
  modelCostPerStartedRunUsd: number | null;
  computeCostPerStartedRunUsd: number | null;
  gpuCostPerStartedRunUsd: number | null;
  meteredCostPerStartedRunUsd: number | null;
  allocatedFixedCostPerStartedRunUsd: number | null;
  allInCostPerStartedRunUsd: number | null;
  costPerSuccessfulRunUsd: number | null;
  allocatedSubscriptionCostPerSuccessfulRunUsd: number | null;
  totalMonthlyCostUsd: number | null;
  expectedMonthlyRevenueUsd: number | null;
  contributionPerStartedRunUsd: number | null;
  monthlyContributionUsd: number | null;
  breakEvenStartedRuns: number | null;
  breakEvenSuccessfulRuns: number | null;
  perRunBudgetStatus: BudgetStatus;
  monthlyBudgetStatus: BudgetStatus;
  unpricedComponents: string[];
};

const finiteNonNegative = (v: number | null) => v === null || (Number.isFinite(v) && v >= 0);
const perMillion = (tokens: number, rate: number | null, label: string, missing: Set<string>): number => {
  if (tokens === 0) return 0;
  if (rate === null) { missing.add(label); return 0; }
  return tokens * rate / 1_000_000;
};

export function calculateExecutionEconomics(input: EconomicsInput): ExecutionEstimate {
  const nonNegative = [
    input.uncachedInputTokensPerAgentAttempt, input.outputTokensPerAgentAttempt,
    input.cacheReadTokensPerAgentAttempt, input.cacheWriteTokensPerAgentAttempt,
    input.agentsPerRun, input.retriesPerAgent, input.plannedRunsPerMonth,
    input.allocatedSubscriptionMonthlyUsd, input.otherFixedMonthlyUsd,
    input.reservedGpuMonthlyUsd, input.gpuCount,
  ];
  if (nonNegative.some(v => !Number.isFinite(v) || v < 0)) throw new Error('Counts and costs must be finite, non-negative numbers.');
  if (!Number.isInteger(input.agentsPerRun) || !Number.isInteger(input.retriesPerAgent) || !Number.isInteger(input.plannedRunsPerMonth) || !Number.isInteger(input.gpuCount)) throw new Error('Agents, retries, planned runs, and GPU count must be whole numbers.');
  if (input.agentsPerRun < 1 || input.gpuCount < 1) throw new Error('At least one agent and one GPU are required.');
  if (input.successRatePercent < 0 || input.successRatePercent > 100 || !Number.isFinite(input.successRatePercent)) throw new Error('Success rate must be between 0 and 100 percent.');
  if (input.subscriptionAllocationPercent < 0 || input.subscriptionAllocationPercent > 100 || !Number.isFinite(input.subscriptionAllocationPercent)) throw new Error('Subscription allocation must be between 0 and 100 percent.');
  if (!finiteNonNegative(input.gpuRateUsdPerGpuHour) || !finiteNonNegative(input.gpuWallClockHoursPerAgentAttempt) || !finiteNonNegative(input.gpuUtilizationPercent) || !finiteNonNegative(input.revenuePerSuccessfulRunUsd) || !finiteNonNegative(input.perRunBudgetUsd) || !finiteNonNegative(input.monthlyBudgetUsd)) throw new Error('Rates, utilization, price, and budgets must be non-negative.');
  if (!finiteNonNegative(input.kernelComputeCostPerStartedRunUsd ?? null)) throw new Error('Kernel compute cost must be non-negative.');
  if (input.gpuUtilizationPercent !== null && (input.gpuUtilizationPercent <= 0 || input.gpuUtilizationPercent > 100)) throw new Error('GPU utilization must be greater than 0 and at most 100 percent.');

  const attemptsPerRun = input.agentsPerRun * (input.retriesPerAgent + 1);
  const successfulRuns = input.plannedRunsPerMonth * input.successRatePercent / 100;
  const allocatedSubscription = input.allocatedSubscriptionMonthlyUsd * input.subscriptionAllocationPercent / 100;
  const fixedMonthly = allocatedSubscription + input.otherFixedMonthlyUsd + input.reservedGpuMonthlyUsd;
  const unpriced = new Set<string>();

  let modelCostPerRun: number | null;
  if (input.workloadKind === 'kernel') {
    modelCostPerRun = 0;
    if (input.plannedRunsPerMonth > 0 && input.kernelComputeCostPerStartedRunUsd == null) unpriced.add('local kernel compute cost per started run');
  } else if (input.provider === 'subscription') {
    modelCostPerRun = null;
    if (input.plannedRunsPerMonth > 0) unpriced.add('subscription quota or overage consumption per model run');
  } else if (input.provider === 'vllm') {
    // vLLM is self-hosted inference: token charges belong to hosting, not an API rate card.
    modelCostPerRun = 0;
  } else {
    const oneAttempt =
      perMillion(input.uncachedInputTokensPerAgentAttempt, input.rates.inputPerMillionUsd, 'uncached input token rate', unpriced) +
      perMillion(input.outputTokensPerAgentAttempt, input.rates.outputPerMillionUsd, 'output token rate', unpriced) +
      perMillion(input.cacheReadTokensPerAgentAttempt, input.rates.cacheReadPerMillionUsd, 'cache-read token rate', unpriced) +
      perMillion(input.cacheWriteTokensPerAgentAttempt, input.rates.cacheWritePerMillionUsd, 'cache-write token rate', unpriced);
    modelCostPerRun = unpriced.size ? null : oneAttempt * attemptsPerRun;
  }

  let gpuCostPerRun: number | null = 0;
  if (input.provider === 'vllm' || input.provider === 'manual') {
    const hasGpuUsage = input.provider === 'vllm' || input.gpuWallClockHoursPerAgentAttempt !== null;
    if (hasGpuUsage && (input.gpuRateUsdPerGpuHour === null || input.gpuWallClockHoursPerAgentAttempt === null || input.gpuUtilizationPercent === null)) {
      gpuCostPerRun = null;
      unpriced.add('GPU hourly rate, runtime, or utilization');
    } else if (hasGpuUsage) {
      const utilization = input.gpuUtilizationPercent! / 100;
      gpuCostPerRun = input.gpuRateUsdPerGpuHour! * input.gpuCount * input.gpuWallClockHoursPerAgentAttempt! / utilization * attemptsPerRun;
    }
  }

  const computeCostPerRun = input.workloadKind === 'kernel'
    ? input.kernelComputeCostPerStartedRunUsd ?? null
    : 0;
  const meteredPerRun = modelCostPerRun === null || gpuCostPerRun === null || computeCostPerRun === null
    ? null
    : modelCostPerRun + gpuCostPerRun + computeCostPerRun;
  const fixedPerRun = input.plannedRunsPerMonth > 0 ? fixedMonthly / input.plannedRunsPerMonth : null;
  const allInPerRun = meteredPerRun === null || fixedPerRun === null ? null : meteredPerRun + fixedPerRun;
  const totalMonthly = input.plannedRunsPerMonth === 0 ? fixedMonthly : meteredPerRun === null ? null : fixedMonthly + meteredPerRun * input.plannedRunsPerMonth;
  const costPerSuccess = successfulRuns > 0 && totalMonthly !== null ? totalMonthly / successfulRuns : null;
  const allocatedSubscriptionPerSuccess = successfulRuns > 0 ? allocatedSubscription / successfulRuns : null;
  const expectedRevenue = input.revenuePerSuccessfulRunUsd === null ? null : successfulRuns * input.revenuePerSuccessfulRunUsd;
  const contributionPerStart = input.revenuePerSuccessfulRunUsd === null || meteredPerRun === null
    ? null
    : input.revenuePerSuccessfulRunUsd * input.successRatePercent / 100 - meteredPerRun;
  const monthlyContribution = expectedRevenue === null || totalMonthly === null ? null : expectedRevenue - totalMonthly;
  const breakEvenStartedRuns = contributionPerStart !== null && contributionPerStart > 0
    ? Math.ceil(fixedMonthly / contributionPerStart)
    : null;
  const breakEvenSuccessfulRuns = breakEvenStartedRuns === null
    ? null
    : breakEvenStartedRuns * input.successRatePercent / 100;
  const budgetStatus = (limit: number | null, value: number | null): BudgetStatus => limit === null ? 'not-set' : value === null ? 'unknown' : value <= limit ? 'within' : 'exceeds';

  return {
    currency: 'USD', harnessId: input.harnessId, provider: input.provider, workloadKind: input.workloadKind, attemptsPerRun,
    expectedSuccessfulRunsPerMonth: successfulRuns,
    allocatedSubscriptionMonthlyUsd: allocatedSubscription,
    allocatedFixedMonthlyUsd: fixedMonthly,
    modelCostPerStartedRunUsd: modelCostPerRun,
    computeCostPerStartedRunUsd: computeCostPerRun,
    gpuCostPerStartedRunUsd: gpuCostPerRun,
    meteredCostPerStartedRunUsd: meteredPerRun,
    allocatedFixedCostPerStartedRunUsd: fixedPerRun,
    allInCostPerStartedRunUsd: allInPerRun,
    costPerSuccessfulRunUsd: costPerSuccess,
    allocatedSubscriptionCostPerSuccessfulRunUsd: allocatedSubscriptionPerSuccess,
    totalMonthlyCostUsd: totalMonthly,
    expectedMonthlyRevenueUsd: expectedRevenue,
    contributionPerStartedRunUsd: contributionPerStart,
    monthlyContributionUsd: monthlyContribution,
    breakEvenStartedRuns,
    breakEvenSuccessfulRuns,
    perRunBudgetStatus: budgetStatus(input.perRunBudgetUsd, allInPerRun),
    monthlyBudgetStatus: budgetStatus(input.monthlyBudgetUsd, totalMonthly),
    unpricedComponents: [...unpriced],
  };
}
