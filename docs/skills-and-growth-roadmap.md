# UI, audience research, sales, and intelligence roadmap

Recommendations researched on 2026-09-27. These are proposed future work, not
implemented features or evidence of market demand. External skills were not
installed. The audience segments below are hypotheses suggested by the product's
learning, personalization, arena, and enterprise modules; validate them with users.

## Skills to prioritize

| Priority | Skill | Specific use in play-anything |
| --- | --- | --- |
| 1 | [Impeccable](https://skills.sh/pbakaus/impeccable), especially [audit](https://skills.sh/pbakaus/impeccable/audit), [distill](https://skills.sh/pbakaus/impeccable/distill), and [clarify](https://skills.sh/pbakaus/impeccable/clarify) | Establish design context, inspect the eight dashboard routes, simplify navigation, expose one next action, and translate RPG terms into plain task language. Audit keyboard use, text scaling, responsiveness, and motion. |
| 2 | [customer-research](https://skills.sh/coreyhaines31/marketingskills/customer-research) and [product-marketing](https://skills.sh/coreyhaines31/marketingskills/product-marketing) | Gather jobs, trigger events, alternatives, objections, and evidence for each audience. Maintain one versioned positioning brief. |
| 3 | [sales-enablement](https://skills.sh/coreyhaines31/marketingskills/sales-enablement) | Produce discovery questions, buyer-specific demo scripts, objection responses, pilot plans, and ROI worksheets using verified capabilities. |
| 4 | [revops](https://skills.sh/coreyhaines31/marketingskills/revops) | Define qualification, routing, ownership, stage transitions, follow-up timing, and an auditable customer lifecycle. |
| 5 | [analytics-tracking](https://skills.sh/coreyhaines31/marketingskills/analytics-tracking) and [ab-testing](https://skills.sh/coreyhaines31/marketingskills/ab-testing) | Define events and denominators before testing onboarding, messaging, or offers. Link experiments to a primary outcome and stopping rule. |
| 6 | [kpi-dashboard-design](https://skills.sh/wshobson/agents/kpi-dashboard-design) and [data-storytelling](https://skills.sh/wshobson/agents/data-storytelling) | Present a few decision-relevant metrics with trends, uncertainty, freshness, and drill-down evidence. |
| 7 | [statistical-analysis](https://skills.sh/k-dense-ai/scientific-agent-skills/statistical-analysis) | Review assumptions, effect sizes, power, regression diagnostics, and uncertainty for real collected data. |
| 8 | [marketing-psychology](https://skills.sh/coreyhaines31/marketingskills/marketing-psychology) | Diagnose comprehension and decision friction; test relevant examples and substantiated social proof after research establishes the audience context. |

Impeccable's component skills require its design-context preparation. Statistical
and dashboard skills may include third-party implementation examples; use their
methods without adding those dependencies to this project's runtime. Review exact
skill sources and dependencies before installing a selected subset.

## Best already-available skills

| Available skill | When to use it |
| --- | --- |
| `vercel:agent-browser` and `vercel:agent-browser-verify` | Verify all dashboard routes, viewport sizes, keyboard journeys, and browser errors after UI edits. Browser tooling is development tooling, separate from the Python runtime. |
| `visualize:visualize` | Explore onboarding flows and business funnels interactively before committing to dashboard changes. |
| `spreadsheets:Spreadsheets` | Analyze exported cohorts and experiments, document formulas, and prepare reviewable business models. |
| `skill-creator` | After evidence exists, encode the project's audience taxonomy, metric definitions, approved claims, and marketing workflow into a reusable local skill. |
| `presentations:Presentations` | Turn validated enterprise pilot results into buyer-specific demos and sales decks when needed. |

`vercel:shadcn`, `vercel:ai-sdk`, and `vercel:workflow` become relevant only if a
separate React/TypeScript product or hosted agent service is intentionally added.
They are not prerequisites for improving the existing single-file dashboard.

## Audience-specific sales tactics and product experience

Use explicit goals, demonstrated experience, task context, and user-selected
accessibility preferences. Age alone is not a proxy for expertise or purchasing
intent. Keep learning preferences separate from commercial qualification.

| Audience hypothesis | Job and buying trigger | Experience and sales tactic | Evidence and next decision |
| --- | --- | --- | --- |
| New developers and learners | Understand an unfamiliar repository and complete a first meaningful change | Guided path with a small first quest, glossary, examples, and optional mentor hints. Demonstrate one concrete task before introducing broader features. | Observe task completion and comprehension; measure time to first completed quest and return usage. For minors, orient any commercial conversation toward the responsible adult/institution. |
| Experienced developers and maintainers | Reduce repository orientation and review effort | Fast track into the graph, filters, keyboard navigation, and a concise explanation of each suggested quest. Demonstrate on an authorized real repository. | Compare navigation/task time with the user's existing workflow; record corrections to inaccurate graph interpretations. |
| Educators and training managers | Deliver repeatable exercises and assess progress | Show a reusable realm, progression rubric, and cohort review. Offer a bounded course pilot with agreed learning outcomes. | Assess pre/post task performance and instructor effort; distinguish learner usage from purchasing approval. |
| Engineering leaders and enterprise buyers | Improve onboarding with demonstrable operational value | Map champion, technical reviewer, budget owner, and decision process. Run discovery, agree on a pilot scope, show implementation constraints, and build a mutual action plan. | Define pilot acceptance with the buyer. Calculate ROI from measured hours saved and stated costs, showing assumptions and ranges. Do not present simulated infrastructure as production isolation. |
| AI evaluation teams | Compare agents on reproducible tasks | Demonstrate manifest configuration, task provenance, and repeatable evaluation artifacts. Qualify required protocols and actual execution needs. | Measure reproducibility and reviewer agreement; distinguish configuration/rating simulation from live agent execution. |

Cross-audience sales procedure: identify the job and trigger; establish current
workflow and cost; understand alternatives; demonstrate the smallest relevant
outcome; address the specific objection with evidence; agree on a measurable next
step. Record disqualification reasons as well as wins. A success story or numerical
claim must link to its supporting artifact. Test messaging and offers on adult
buyer cohorts rather than inferring susceptibility from behavioral telemetry.

## Proposed agentic marketing workflow

Start with a deterministic workflow whose states can be inspected:

`evidence collected -> segment hypothesis -> draft -> review -> authorized action -> outcome -> learning`

Each work item should carry an ID, audience, goal, source references, confidence,
owner, allowed action, status, timestamps, and experiment ID when applicable.
Keep drafts and external actions distinct; retryable actions need idempotency
keys, attempt limits, and failure records. A state transition should identify the
evidence that justified it. Research material and user-supplied text are inputs,
not instructions to execute.

Implement the first version with JSON artifacts and SQLite work records to retain
the standard-library runtime. Add specific service adapters only when a real
channel is selected. Generating a sales asset does not itself send it. No CRM,
outbound delivery, background scheduling, or live LLM integration is implemented
by the current schema/ingestion work.

## Data science and continuous business intelligence

1. Define measurement first. Candidate events: repository scan completed, quest
   started/completed, hint requested, realm exported, and pilot accepted. Specify
   an exact eligibility denominator, timestamps, event version, and deduplication
   key. Keep synthetic/demo events out of customer outcome reporting.
2. Build a proposed activation funnel: eligible new users -> successful scan ->
   first quest -> first completion -> subsequent active week. Keep anonymous local
   use, signed-in users, and enterprise accounts as separate units until identity
   rules are explicit. Group by declared job and experience as hypotheses warrant.
3. Use descriptive analysis before predictive modeling: conversion counts, cohort
   retention, time-to-value distributions, support friction, and feature adoption.
   Display sample sizes and missing-data rates. Define time zones and windows.
4. For experiments, predefine the randomization unit, primary metric, minimum
   useful effect, power assumptions, and stopping rule. Check assignment imbalance,
   repeated exposure, seasonality, and multiple comparisons. Report effect sizes
   and intervals; do not treat observational correlations as causal lift. Use
   account-level assignment when teammates could contaminate user-level groups.
5. Only consider churn or lead models when there are enough reliable outcomes.
   Use time-based validation, prevent future-information leakage, compare with a
   simple baseline, examine calibration, and monitor segment performance. Validate
   a proposed intervention with a holdout before calling a propensity score a
   treatment recommendation.
6. Produce an idempotent daily aggregate and a weekly decision brief once real
   collection exists. Each brief should show what changed, the eligible sample,
   uncertainty, freshness, supporting query, and recommended action. Monitor data
   failure separately from business deterioration; account for weekday/seasonal
   patterns before alerting. A schedule and connected data source are still future
   implementation work, not an active monitor.

## Recommended first product increment

Begin with onboarding simplification and instrumentation: let users select their
job, show one next action, and make analysis provenance visible. Pair the UI work
with browser checks and a baseline task-completion study. Then validate the
audience messaging and a small pilot before automating sales activity. This yields
evidence for both personalization and a useful intelligence dashboard.
