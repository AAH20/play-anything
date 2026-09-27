'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  calculateExecutionEconomics,
  OPENROUTER_RATE_CARDS,
  type ExecutionEstimate,
  type RateCard,
  type TokenRates,
} from '@/lib/execution-economics';
import { harnessCatalog, type HarnessId, type ProviderMode } from '@/lib/harness-catalog';

export type { ExecutionEstimate } from '@/lib/execution-economics';

type Props = {
  harnessId?: HarnessId;
  provider?: ProviderMode;
  workloadKind?: 'kernel' | 'model' | 'framework' | 'harness';
  onEstimate?: (estimate: ExecutionEstimate | null) => void;
};

const rateCardById = new Map(OPENROUTER_RATE_CARDS.map(card => [card.id, card]));
const starterCard = OPENROUTER_RATE_CARDS[0];
const parseOptional = (value: string): number | null => value.trim() === '' ? null : Number(value);
const currency = (value: number | null) => value === null || !Number.isFinite(value)
  ? 'Unknown'
  : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 6 }).format(value);
const numberInput = (label: string, value: string, onChange: (next: string) => void, props: { min?: number; max?: number; step?: number; help?: string; disabled?: boolean } = {}) => (
  <label className="economics-field" key={label}>
    <span>{label}</span>
    <input type="number" min={props.min ?? 0} max={props.max} step={props.step ?? 'any'} value={value} onChange={event => onChange(event.target.value)} disabled={props.disabled} />
    {props.help && <small>{props.help}</small>}
  </label>
);

export default function ExecutionEconomics({ harnessId: controlledHarness, provider: controlledProvider, workloadKind, onEstimate }: Props) {
  const [localHarness, setLocalHarness] = useState<HarnessId>('codex');
  const [localProvider, setLocalProvider] = useState<ProviderMode>('openrouter');
  const harnessId = controlledHarness ?? localHarness;
  const provider = workloadKind === 'kernel' ? 'manual' : controlledProvider ?? localProvider;
  const [cardId, setCardId] = useState(starterCard.id);
  const selectedCard = rateCardById.get(cardId) ?? starterCard;
  const [rates, setRates] = useState<TokenRates>(selectedCard.rates);
  const [inputTokens, setInputTokens] = useState('10000');
  const [outputTokens, setOutputTokens] = useState('2000');
  const [cacheReadTokens, setCacheReadTokens] = useState('0');
  const [cacheWriteTokens, setCacheWriteTokens] = useState('0');
  const [agents, setAgents] = useState('1');
  const [retries, setRetries] = useState('0');
  const [success, setSuccess] = useState('90');
  const [monthlyRuns, setMonthlyRuns] = useState('100');
  const [subscription, setSubscription] = useState('');
  const [kernelCompute, setKernelCompute] = useState('');
  const [subscriptionAllocation, setSubscriptionAllocation] = useState('100');
  const [otherFixed, setOtherFixed] = useState('0');
  const [reservedGpu, setReservedGpu] = useState('');
  const [gpuRate, setGpuRate] = useState('');
  const [gpuCount, setGpuCount] = useState('1');
  const [gpuHours, setGpuHours] = useState('');
  const [gpuUtilization, setGpuUtilization] = useState('');
  const [revenue, setRevenue] = useState('');
  const [perRunBudget, setPerRunBudget] = useState('');
  const [monthlyBudget, setMonthlyBudget] = useState('');

  useEffect(() => {
    setRates(provider === 'openrouter'
      ? selectedCard.rates
      : { inputPerMillionUsd: null, outputPerMillionUsd: null, cacheReadPerMillionUsd: null, cacheWritePerMillionUsd: null });
  }, [cardId, provider, selectedCard]);

  const estimate = useMemo(() => {
    try {
      return calculateExecutionEconomics({
        harnessId, provider, workloadKind, rates,
        kernelComputeCostPerStartedRunUsd: parseOptional(kernelCompute),
        uncachedInputTokensPerAgentAttempt: workloadKind === 'kernel' ? 0 : Number(inputTokens),
        outputTokensPerAgentAttempt: workloadKind === 'kernel' ? 0 : Number(outputTokens),
        cacheReadTokensPerAgentAttempt: workloadKind === 'kernel' ? 0 : Number(cacheReadTokens),
        cacheWriteTokensPerAgentAttempt: workloadKind === 'kernel' ? 0 : Number(cacheWriteTokens),
        agentsPerRun: Number(agents), retriesPerAgent: Number(retries),
        successRatePercent: Number(success), plannedRunsPerMonth: Number(monthlyRuns),
        allocatedSubscriptionMonthlyUsd: parseOptional(subscription) ?? 0,
        subscriptionAllocationPercent: Number(subscriptionAllocation),
        otherFixedMonthlyUsd: Number(otherFixed), reservedGpuMonthlyUsd: parseOptional(reservedGpu) ?? 0,
        gpuRateUsdPerGpuHour: parseOptional(gpuRate), gpuCount: Number(gpuCount),
        gpuWallClockHoursPerAgentAttempt: parseOptional(gpuHours), gpuUtilizationPercent: parseOptional(gpuUtilization),
        revenuePerSuccessfulRunUsd: parseOptional(revenue), perRunBudgetUsd: parseOptional(perRunBudget),
        monthlyBudgetUsd: parseOptional(monthlyBudget),
      });
    } catch {
      return null;
    }
  }, [harnessId, provider, workloadKind, rates, inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, agents, retries, success, monthlyRuns, subscription, kernelCompute, subscriptionAllocation, otherFixed, reservedGpu, gpuRate, gpuCount, gpuHours, gpuUtilization, revenue, perRunBudget, monthlyBudget]);

  useEffect(() => { onEstimate?.(estimate); }, [estimate, onEstimate]);

  function changeRate(key: keyof TokenRates, value: string) {
    setRates(previous => ({ ...previous, [key]: parseOptional(value) }));
  }

  const displayCard: RateCard | undefined = provider === 'openrouter' ? selectedCard : undefined;
  return <section className="execution-economics" aria-labelledby="execution-economics-title">
    <header className="economics-heading">
      <div><span className="eyebrow">COST MODEL · ESTIMATE ONLY</span><h3 id="execution-economics-title">Execution economics</h3>
        <p>Editable planning assumptions. Results are estimates, not provider invoices or entitlement guarantees.</p>
      </div>
    </header>
    <div className="economics-controls">
      {controlledHarness === undefined && <label className="economics-field"><span>Harness</span><select value={localHarness} onChange={event => setLocalHarness(event.target.value as HarnessId)}>{harnessCatalog.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}
      {controlledProvider === undefined && <label className="economics-field"><span>Billing provider</span><select value={localProvider} onChange={event => setLocalProvider(event.target.value as ProviderMode)}><option value="gateway">AI Gateway / provider API</option><option value="openrouter">OpenRouter API</option><option value="vllm">Self-hosted vLLM</option><option value="subscription">Subscription / account plan</option><option value="manual">Manual / custom</option></select></label>}
      {provider === 'openrouter' && workloadKind !== 'kernel' && <label className="economics-field"><span>Reference model rate card</span><select value={cardId} onChange={event => setCardId(event.target.value)}>{OPENROUTER_RATE_CARDS.map(card => <option value={card.id} key={card.id}>{card.label}</option>)}</select></label>}
    </div>
    {displayCard && workloadKind !== 'kernel' && <details className="economics-provenance" open><summary>Rate provenance</summary><p><a href={displayCard.sourceUrl} target="_blank" rel="noreferrer">OpenRouter public model catalog</a>, checked {displayCard.checkedAt}. Model rate reference: <code>{displayCard.modelId}</code>.</p>{displayCard.note && <p>{displayCard.note}</p>}<p>Execution model is configured separately by the server. This selected model is only a cost-rate assumption.</p></details>}
    {workloadKind === 'kernel' && <p className="economics-notice">This is a local Python kernel run. Model token charges are fixed at $0 for this estimate; local compute attribution remains unknown until you enter it below. No external model provider is inferred.</p>}
    {provider === 'subscription' && <p className="economics-notice">Subscription access is not priced as unlimited API usage. Enter only the share of your fixed plan cost allocated to this workload; quota consumption, included limits, and overages remain unknown unless separately measured.</p>}
    {provider === 'vllm' && <p className="economics-notice">vLLM token inference is self-hosted. Enter GPU hourly price, wall-clock GPU time, and utilization; GPU hosting is costed separately from API token rates.</p>}

    <div className="economics-grid">
      <fieldset><legend>Usage per agent attempt</legend>
        {numberInput('Uncached input tokens', workloadKind === 'kernel' ? '0' : inputTokens, setInputTokens, { help: workloadKind === 'kernel' ? 'Local kernel workload; no model request is assumed.' : 'Example assumption; replace with measured usage.', disabled: workloadKind === 'kernel' })}
        {numberInput('Output tokens', workloadKind === 'kernel' ? '0' : outputTokens, setOutputTokens, { disabled: workloadKind === 'kernel' })}
        {numberInput('Cache-read tokens', workloadKind === 'kernel' ? '0' : cacheReadTokens, setCacheReadTokens, { disabled: workloadKind === 'kernel' })}
        {numberInput('Cache-write tokens', workloadKind === 'kernel' ? '0' : cacheWriteTokens, setCacheWriteTokens, { disabled: workloadKind === 'kernel' })}
      </fieldset>
      <fieldset><legend>Fanout and workload</legend>
        {numberInput('Agents per run', agents, setAgents, { min: 1, step: 1 })}
        {numberInput('Retries per agent', retries, setRetries, { step: 1 })}
        {numberInput('Successful run rate (%)', success, setSuccess, { max: 100, help: 'Expected completed runs divided by started runs.' })}
        {numberInput('Started runs per month', monthlyRuns, setMonthlyRuns, { step: 1 })}
      </fieldset>
      <fieldset><legend>Editable rates · USD per 1M tokens</legend>
        {numberInput('Uncached input rate', rates.inputPerMillionUsd === null ? '' : String(rates.inputPerMillionUsd), value => changeRate('inputPerMillionUsd', value), { disabled: workloadKind === 'kernel' })}
        {numberInput('Output rate', rates.outputPerMillionUsd === null ? '' : String(rates.outputPerMillionUsd), value => changeRate('outputPerMillionUsd', value), { disabled: workloadKind === 'kernel' })}
        {numberInput('Cache-read rate', rates.cacheReadPerMillionUsd === null ? '' : String(rates.cacheReadPerMillionUsd), value => changeRate('cacheReadPerMillionUsd', value), { disabled: workloadKind === 'kernel' })}
        {numberInput('Cache-write rate', rates.cacheWritePerMillionUsd === null ? '' : String(rates.cacheWritePerMillionUsd), value => changeRate('cacheWritePerMillionUsd', value), { help: 'Blank means unknown, not free.', disabled: workloadKind === 'kernel' })}
      </fieldset>
      <fieldset><legend>Fixed and local hosting costs</legend>
        {workloadKind === 'kernel' && numberInput('Local kernel compute cost per started run (USD)', kernelCompute, setKernelCompute, { help: 'Enter measured/allocated machine cost. Blank keeps totals unknown; 0 is an explicit zero-cost assumption.' })}
        {numberInput('Monthly subscription price', subscription, setSubscription, { help: 'Blank means unentered; use the portion actually attributable to this workload.' })}
        {numberInput('Subscription allocation (%)', subscriptionAllocation, setSubscriptionAllocation, { max: 100 })}
        {numberInput('Other fixed monthly cost', otherFixed, setOtherFixed)}
        {numberInput('Reserved GPU monthly cost', reservedGpu, setReservedGpu, { help: 'For reserved capacity; leave blank if not applicable.' })}
      </fieldset>
      {provider === 'vllm' && <fieldset><legend>vLLM GPU cost</legend>
        {numberInput('GPU price (USD/GPU-hour)', gpuRate, setGpuRate, { help: `RunPod Secure H100 SXM reference: $3.49/GPU-hour, checked ${'2026-09-13'}; enter your actual quote.` })}
        {numberInput('GPUs used concurrently', gpuCount, setGpuCount, { min: 1, step: 1 })}
        {numberInput('GPU wall-clock hours per agent attempt', gpuHours, setGpuHours, { help: 'Elapsed allocation time, not just kernel-active time.' })}
        {numberInput('Utilization (%)', gpuUtilization, setGpuUtilization, { max: 100, help: 'Cost is amortized over this share of allocated GPU time.' })}
      </fieldset>}
      <fieldset><legend>Business and budget</legend>
        {numberInput('Revenue per successful run (USD)', revenue, setRevenue)}
        {numberInput('Budget per started run (USD)', perRunBudget, setPerRunBudget)}
        {numberInput('Monthly budget (USD)', monthlyBudget, setMonthlyBudget)}
      </fieldset>
    </div>
    <div className="economics-results" aria-live="polite">
      <div><span>Attempts / run</span><strong>{estimate?.attemptsPerRun ?? '—'}</strong></div>
      <div><span>Metered cost / started run</span><strong>{currency(estimate?.meteredCostPerStartedRunUsd ?? null)}</strong></div>
      {workloadKind === 'kernel' && <div><span>Local compute / started run</span><strong>{currency(estimate?.computeCostPerStartedRunUsd ?? null)}</strong></div>}
      <div><span>All-in cost / started run</span><strong>{currency(estimate?.allInCostPerStartedRunUsd ?? null)}</strong></div>
      <div><span>Cost / successful run</span><strong>{currency(estimate?.costPerSuccessfulRunUsd ?? null)}</strong></div>
      <div><span>Monthly total</span><strong>{currency(estimate?.totalMonthlyCostUsd ?? null)}</strong></div>
      <div><span>Subscription allocated / month</span><strong>{currency(estimate?.allocatedSubscriptionMonthlyUsd ?? null)}</strong></div>
      <div><span>Contribution / started run</span><strong>{currency(estimate?.contributionPerStartedRunUsd ?? null)}</strong></div>
      <div><span>Monthly contribution</span><strong>{currency(estimate?.monthlyContributionUsd ?? null)}</strong></div>
      <div><span>Break-even started runs / month</span><strong>{estimate?.breakEvenStartedRuns ?? 'Unknown'}</strong></div>
      <div><span>Break-even successful runs / month</span><strong>{estimate?.breakEvenSuccessfulRuns ?? 'Unknown'}</strong></div>
      <div><span>Per-run budget</span><strong>{estimate?.perRunBudgetStatus ?? '—'}</strong></div>
      <div><span>Monthly budget</span><strong>{estimate?.monthlyBudgetStatus ?? '—'}</strong></div>
    </div>
    {estimate?.unpricedComponents.length ? <p className="economics-notice"><strong>Unpriced:</strong> {estimate.unpricedComponents.join('; ')}. Calculated totals that depend on these values are shown as unknown.</p> : null}
    <p className="economics-footnote">Retries and fanout multiply each per-attempt token/GPU assumption. Fixed costs are allocated over planned monthly runs; zero planned runs keeps fixed spend visible and leaves per-run costs unknown. All USD values are estimates and exclude taxes, provider-specific discounts, tier thresholds, and ancillary infrastructure unless entered.</p>
  </section>;
}
