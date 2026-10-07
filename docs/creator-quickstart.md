# Creator quick start

Start the local workbench:

```bash
python3 -m play_anything.creator_server
```

It opens a browser on loopback port 8765. Use `--port 0` for an automatically
selected free port, `--no-browser` to print the URL without opening it, or
`--workspace-root /your/chosen/directory` to choose where clones are created.
`python3 -m play_anything.cli creator` is an equivalent entry point.

The existing dashboard also has a **Creator quick start** tab at `#quickstart`.
Opening `creator.html` directly supports the sample and plan export. Live model
connections and Git cloning require the local service. Git must be installed;
Python packages are not required.

## The four steps

1. **Connect & start.** Choose a game, map, or developer-tool goal and a guided or
   experienced path. Absolute quick start opens an explicitly illustrative sample
   with no credentials. Otherwise choose your existing agent/harness by name and
   prepare a downloadable handoff, or verify a compatible model endpoint.
2. **Understand.** Enter a public HTTPS GitHub, GitLab, or Bitbucket repository URL.
   The service shallow-clones it into a managed analysis directory and inspects up
   to 500 supported files. Explore folders, measured line counts, Python ASTs, and
   actual resolvable imports. Complete two understanding checks before proceeding.
3. **Compose.** Select from 19 capabilities covering the existing subsystems and
   the creator workflow. Dependencies are automatically included. Presets suit
   games, maps, or developer tools. Choose source areas for your agent to focus on.
4. **Build a business.** Edit setup effort, labor rates, fixed overhead, variable
   costs, customer volumes, price, fees, refunds, acquisition, and model usage.
   Review the accounting, official engine comparisons, and your own competitors.
   Export a plan, or create a separate Git clone plus `venture-plan.json` and
   `AGENT-HANDOFF.md`. The mentorship link opens a draft to **aah@a2zsoc.com** in the
   user's mail client; the application does not send mail.

## Agent and harness support

Handoff mode supports any harness that can consume a Markdown brief and JSON
plan. It does not pretend to authenticate or launch that harness. The endpoint
mode calls `GET <base>/models` and `POST <base>/chat/completions` using the selected
model. Native provider protocols that differ need a compatible gateway. HTTP is
accepted for localhost; remote endpoints require HTTPS. Redirects are rejected.

Keys and live connection IDs stay in server/browser memory, never in saved
onboarding state or exports. Reconnect after a browser reload. The explanation
button sends at most 60 file summaries and 100 import relationships; it sends no
source file contents. Explanations are model output, not verified execution.

## Modularization scope

Selections are a dependency-aware implementation brief. They do not dynamically
extract an arbitrary repository into independently runnable packages. The clone
retains all code, dependencies, and license files; an agent can use the plan to
implement and verify the selected capabilities. Existing simulated infrastructure
remains simulated. Non-Python files have measured line counts, not parsed imports.
Module card costs are illustrative monthly allowances before shared costs.

Public availability is not a commercial license. The report shows root license
files, while the creator confirms that code, assets, and branding permissions
match their intended use. License detection does not automatically certify reuse.
Private repositories, arbitrary/self-hosted Git servers, automatic deployment,
and automatic execution of repository code are not supported by this increment.

## Accounting assumptions

All inputs are USD and monthly unless marked as setup. Default figures are
illustrative allowances, not current vendor quotes or earnings forecasts. Every
selected module has editable setup hours, monthly fixed cost, and variable cost
per active user. Setup hours are multiplied by the shared hourly labor rate.

- Revenue = paying customers × monthly price.
- Refunds and percentage fees are applied to gross revenue; payment fees are
  conservatively retained on refunded transactions. Each paying customer creates
  one fixed-fee transaction per month.
- Module variable costs apply to all active users, including nonpaying users.
- Model cost = active users × (input tokens × input rate + output tokens × output
  rate) / 1,000,000, when the agent bridge module is selected. Other provider costs
  belong in module allowances.
- Contribution = revenue − refunds − fees − module variable costs − model cost.
- Operating result = contribution − module fixed costs − maintenance labor −
  overhead − acquisition spend.
- CAC = acquisition spend / newly acquired customers.
- Break-even holds the paid-to-active ratio constant and divides the fixed costs
  plus acquisition spend by contribution per paying customer, rounded up. Zero or
  negative contribution has no finite break-even under that scenario.
- Setup payback assumes a stable, positive monthly operating result. Taxes,
  depreciation, financing, and nonlinear engine royalties are not automatically
  modeled. Enter relevant allowances; check each vendor's actual terms.

Python uses Decimal arithmetic; browser calculations use JavaScript numbers.
Backend estimates use a local Decimal context with 50 significant digits,
independent of the caller's precision, rounding, exponent settings, or traps.
The JSON plan retains the existing six-decimal half-even output policy. Arithmetic underflow/overflow and ratios outside finite
numeric output range return a controlled error. Exact zero usage or price remains
valid. Break-even counts must fit at most 4,300 decimal digits, or the interpreter's
smaller configured JSON integer limit. Hosting inputs that would silently become
zero during Decimal-to-float conversion are rejected. These bounds describe the
calculator's supported representation, not a minimum commercial price.

Display rounds money to cents; very small nonzero inputs can round to zero in
the six-place JSON summary. Preserve the original inputs when reproducing a
scenario. Six ordinary cross-runtime scenarios were checked for agreement within
0.000002 USD; that observation is not an all-input precision guarantee. Outputs
are scenario calculations, not audited books.

## Comparisons and learning signals

Godot, Unity, and Unreal are engine ecosystem references for game/map creators.
Official licensing sources are linked and dated in the UI. Entry barriers and
possible moats are labeled hypotheses. A custom comparison accepts a direct
competitor name, evidence URL, barrier, and defensibility notes for another industry.

Activation events are recorded locally: quick start, agent configuration, analysis,
tutorial completion, export, workspace creation, and opening the mentorship link.
Each event has an ID and a sample flag. Browser storage retains up to 1,000 events;
the running service retains up to 1,000 deduplicated events at `GET /api/events`.
There is no external analytics delivery or persistent cross-session server identity.
Exclude sample events from real activation reporting. Reanalyze real repositories
after restarting the service; locally saved scenarios can still be edited/exported.

## Verification

```bash
python3 -m unittest discover tests
python3 tests/creator_smoke.py
node --check play_anything/creator.js
node --check play_anything/creator-model.js
```

The optional smoke test requires Git and loopback binding. It uses a temporary
repository and local model fixture to verify real HTTP requests, session checks,
model verification/explanation, tutorial gating, Git cloning, license preservation,
and plan/handoff creation. It does not call a paid model.

Browser checks should cover all four creator steps, invalid tutorial answers,
dependency inclusion, recalculation, export, offline sample use, mobile overflow,
mentorship links, and the existing dashboard hashes plus `#quickstart`.
