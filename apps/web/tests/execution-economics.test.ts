import assert from 'node:assert/strict';
import test from 'node:test';
import { calculateExecutionEconomics, OPENROUTER_RATE_CARDS, type EconomicsInput } from '../lib/execution-economics';

const base = (): EconomicsInput => ({
  harnessId: 'codex', provider: 'openrouter',
  rates: { inputPerMillionUsd: 1, outputPerMillionUsd: 6, cacheReadPerMillionUsd: 0.1, cacheWritePerMillionUsd: 0.5 },
  uncachedInputTokensPerAgentAttempt: 10_000, outputTokensPerAgentAttempt: 2_000,
  cacheReadTokensPerAgentAttempt: 1_000, cacheWriteTokensPerAgentAttempt: 500,
  agentsPerRun: 2, retriesPerAgent: 1, successRatePercent: 80, plannedRunsPerMonth: 100,
  allocatedSubscriptionMonthlyUsd: 0, subscriptionAllocationPercent: 100,
  otherFixedMonthlyUsd: 0, reservedGpuMonthlyUsd: 0,
  gpuRateUsdPerGpuHour: null, gpuCount: 1, gpuWallClockHoursPerAgentAttempt: null,
  gpuUtilizationPercent: null, revenuePerSuccessfulRunUsd: 1,
  perRunBudgetUsd: null, monthlyBudgetUsd: null,
});

test('fanout and retries multiply token costs and provide monthly economics', () => {
  const result = calculateExecutionEconomics(base());
  // 4 attempts × ($0.010 input + $0.012 output + $0.0001 cached read + $0.00025 cache write)
  assert.equal(result.attemptsPerRun, 4);
  assert.ok(Math.abs((result.modelCostPerStartedRunUsd ?? 0) - 0.0894) < 1e-12);
  assert.equal(result.expectedSuccessfulRunsPerMonth, 80);
  assert.ok(Math.abs((result.costPerSuccessfulRunUsd ?? 0) - 0.11175) < 1e-12);
  assert.equal(result.monthlyContributionUsd, 71.06);
  assert.equal(result.breakEvenStartedRuns, 0);
});

test('zero monthly volume reports fixed spend while per-run allocation is unknown', () => {
  const input = base();
  input.plannedRunsPerMonth = 0;
  input.allocatedSubscriptionMonthlyUsd = 60;
  input.subscriptionAllocationPercent = 25;
  input.otherFixedMonthlyUsd = 8;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.allocatedSubscriptionMonthlyUsd, 15);
  assert.equal(result.totalMonthlyCostUsd, 23);
  assert.equal(result.allocatedFixedCostPerStartedRunUsd, null);
  assert.equal(result.costPerSuccessfulRunUsd, null);
});

test('low success rate raises cost per successful run and can make breakeven unreachable', () => {
  const input = base();
  input.successRatePercent = 5;
  input.revenuePerSuccessfulRunUsd = 0.01;
  input.otherFixedMonthlyUsd = 50;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.expectedSuccessfulRunsPerMonth, 5);
  assert.ok((result.costPerSuccessfulRunUsd ?? 0) > 10);
  assert.equal(result.breakEvenStartedRuns, null);
  assert.equal(result.breakEvenSuccessfulRuns, null);
});

test('subscription cost keeps allocated plan spend separate and model usage unknown', () => {
  const input = base();
  input.provider = 'subscription';
  input.allocatedSubscriptionMonthlyUsd = 40;
  input.subscriptionAllocationPercent = 50;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.allocatedSubscriptionMonthlyUsd, 20);
  assert.equal(result.modelCostPerStartedRunUsd, null);
  assert.equal(result.totalMonthlyCostUsd, null);
  assert.ok(result.unpricedComponents.includes('subscription quota or overage consumption per model run'));
});

test('missing cache-write price is unknown when cache-write tokens are present', () => {
  const input = base();
  input.rates = OPENROUTER_RATE_CARDS[0].rates;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.modelCostPerStartedRunUsd, null);
  assert.ok(result.unpricedComponents.includes('cache-write token rate'));
  assert.equal(result.monthlyBudgetStatus, 'not-set');
});

test('vLLM cost uses GPU wall time and amortizes over utilization', () => {
  const input = base();
  input.provider = 'vllm';
  input.gpuRateUsdPerGpuHour = 3.49;
  input.gpuCount = 1;
  input.gpuWallClockHoursPerAgentAttempt = 0.25;
  input.gpuUtilizationPercent = 50;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.modelCostPerStartedRunUsd, 0);
  assert.equal(result.gpuCostPerStartedRunUsd, 6.98);
});

test('native kernels never inherit model-token charges and leave compute unpriced until entered', () => {
  const input = base();
  input.workloadKind = 'kernel';
  input.provider = 'manual';
  input.kernelComputeCostPerStartedRunUsd = null;
  const unknown = calculateExecutionEconomics(input);
  assert.equal(unknown.modelCostPerStartedRunUsd, 0);
  assert.equal(unknown.computeCostPerStartedRunUsd, null);
  assert.equal(unknown.totalMonthlyCostUsd, null);
  assert.ok(unknown.unpricedComponents.includes('local kernel compute cost per started run'));

  input.kernelComputeCostPerStartedRunUsd = 0.002;
  const priced = calculateExecutionEconomics(input);
  assert.equal(priced.meteredCostPerStartedRunUsd, 0.002);
  assert.equal(priced.totalMonthlyCostUsd, 0.2);
});

test('budget checks flag estimates over configured limits', () => {
  const input = base();
  input.perRunBudgetUsd = 0.001;
  input.monthlyBudgetUsd = 0.1;
  const result = calculateExecutionEconomics(input);
  assert.equal(result.perRunBudgetStatus, 'exceeds');
  assert.equal(result.monthlyBudgetStatus, 'exceeds');
});

test('invalid utilization is rejected instead of producing misleading estimates', () => {
  const input = base();
  input.provider = 'vllm';
  input.gpuUtilizationPercent = 0;
  assert.throws(() => calculateExecutionEconomics(input), /GPU utilization/);
});
