# Repository intelligence, pitching and hosting

## What is implemented

`dashboard.html#graph` is a new repository relationship explorer. The existing RPG map remains at `#map`. The same graph component is embedded in Creator phase 2, **Understand the repo**. Analyze a public repository there, or analyze this project directly in the graph view. Export/import complete indexed graph JSON to move analysis into a hosted site.

The graph inventories files, directory modules, functions and classes. Python ASTs supply definitions, imports, lexical calls and inheritance with source locations. `self`/`cls` calls and JavaScript/TypeScript declaration/import hints are explicitly inferred. Dynamic dispatch, re-exports and unsupported syntax can remain unresolved. This is static evidence, not a runtime trace or a complete parser for every language. Search, relationship filters, module aggregation, a node inspector and neighborhood focus reduce visual complexity. All indexed nodes are reachable by pagination or search; 36 are rendered at once.

Git repositories honor tracked files and `.gitignore` for untracked files. Generated/vendor directories and symlinks are excluded. Default bounds: 2,000 files, 10,000 symbols, source parsing up to 1 MB per file. Limits, syntax failures and unresolved calls are disclosed. Larger repositories require a scoped scan or a future on-disk graph index. Sample walkthrough graphs are labeled illustrative.

Phase 3 selects 20 capabilities, including the **Investor pitch & presentation studio**, with dependency closure. Its cost table shows setup labor, direct monthly costs, an explicitly equal allocation of shared costs, per-paying-customer cost and the incremental cost of adding each remaining option with missing dependencies. Phase 4 lets creators edit assumptions and module allowances. Both phases share the same hosting selection and accounting state.

The pitch module produces audience-specific slide outlines, a spoken narrative, practice questions, evidence checklists and timed rehearsal. It supports investor committees/Shark Tank-style presentations, PE committees, investment bankers and a 1:1 elevator conversation. Markdown and printable HTML exports preserve explicit evidence gaps. PE and banking templates request historical financials and transaction context; calculator results remain clearly identified as scenarios. No unsupported valuation, market size, traction or investor personality claims are generated.

## Deploy the static site

Preparation is complete; no provider resources have been created or deployed.

```sh
python3 scripts/build_site.py
```

The `site-dist` bundle contains only allowlisted assets and a graph snapshot of this repository. Review the snapshot before publishing a private project: it includes file paths, symbol names and short docstrings. Build output is ignored by Git. The legacy dashboard still uses its existing CDN resources; this preparation does not make that dashboard offline-complete.

- **Vercel:** import this repository, use the checked-in `vercel.json`, and leave framework preset as Other. Build: `python3 scripts/build_site.py`; output: `site-dist`. Choose Pro for commercial use. Hobby is restricted to personal, non-commercial use.
- **Cloudflare Pages:** connect the repository, use `python3 scripts/build_site.py`, and set output to `site-dist`. Or build locally and explicitly publish with `npx wrangler pages deploy site-dist`. `wrangler.toml` describes the output directory. The static app needs no Worker.

The hosted site supports planning, pitch preparation, graph snapshots/import and optional Supabase plan persistence. Git cloning, source analysis and compatible model connections run in the local stdlib service:

```sh
python3 -m play_anything.creator_server
```

A static deployment cannot run that long-lived Python/Git service. Live remote analysis would require a separately secured job service; the paid Worker option in the estimator does not create one.

## Optional Supabase plan storage

1. Create/select your own Supabase project and review its tier. No project is selected automatically.
2. Apply `supabase/migrations/20260927035159_creator_plan_vault.sql` using the Supabase SQL editor, or link the CLI to the intended project and use the migration workflow. Apply only after reviewing the target project.
3. Enable email/password Auth and create/invite the desired users. This UI signs into existing accounts; it does not implement public signup or password recovery.
4. Set **public** build variables `SUPABASE_URL=https://PROJECT.supabase.co` and `SUPABASE_PUBLISHABLE_KEY=sb_publishable_...`, then rebuild. The build rejects secret and legacy JWT keys. Never add a service-role key to the static site.
5. Sign in under phase 4, save a snapshot, and load your plan on another device. Access tokens stay in tab memory. Expired sessions require sign-in again. A save includes module/cost/pitch/competitor planning fields; model credentials, source code and graph contents are excluded.

The migration enables and forces row-level security. Explicit authenticated-only SELECT/INSERT/UPDATE/DELETE policies match `auth.uid()` to `user_id`. Updates check both the existing and new owner; anonymous access is revoked. Snapshot payloads are bounded to 256 KB. Supabase project lifecycle, backups, abuse controls and account recovery are managed in your provider account.

## Cost methodology and sources

Rates checked **2026-09-27**, USD before tax. Exact arithmetic is applied to explicit assumptions; it is not an exact future invoice. Hosting is included once in the fixed-cost bucket. Shared per-module allocation is a reporting convention; the incremental option calculation uses the total plan difference. Break-even is a scenario at the current hosting usage input, not a forecast across future tier jumps.

- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/): free static hosting, 500 builds/month, 25 MiB maximum asset size. Static requests are free; [optional Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/) is modeled separately ($5 base, request and CPU overages).
- [Vercel Hobby](https://vercel.com/docs/plans/hobby): personal, non-commercial only. [Pro](https://vercel.com/docs/plans/pro-plan): $20 platform fee including one deploying seat and $20 eligible usage credit; additional deploying seats $20 each. Enter estimated eligible metered usage; the calculator subtracts the credit once. Other add-ons use a separate allowance.
- [Supabase pricing](https://supabase.com/pricing): Free includes 50,000 MAU, 500 MB database, 1 GB storage, 5 GB uncached and 5 GB cached egress; up to two active projects, with inactivity pausing. Pro starts at $25 for the modeled one-Micro-project scenario and has usage allowances/overages. Free-limit violations require a plan change; they are not silently billed at Pro rates. Realtime, Edge Functions, extra compute/projects, email, logs, backups and domains need additional estimates.
- [Sequoia business-plan guidance](https://sequoiacap.com/article/writing-a-business-plan) and [YC pitch guidance](https://www.ycombinator.com/blog/guide-to-demo-day-pitches/) inform the pitch structure. Audience emphasis is a preparation framework, not personal psychological profiling.

## Verification

Validation on 2026-09-27: 73 unit tests pass; a quiet run took 0.048s (concurrent browser/build activity produced slower runs). The Python/JavaScript catalog and accounting agree across five local, free, paid and quota-exceeded scenarios. Browser checks covered graph search/focus, the real phase-2 graph, phase-3/4 hosting totals, pitch audience selection, static snapshots and mobile overflow. RLS policies passed PostgreSQL WASM tests; live cloud Auth is not yet provisioned.

```sh
python3 -m unittest discover tests
python3 -m py_compile play_anything/core/repository_graph.py play_anything/core/hosting_costs.py play_anything/core/venture_planner.py play_anything/creator_server.py scripts/build_site.py
```

An optional development-only SQL verification runs a real PostgreSQL WASM engine without adding application dependencies:

```sh
npm install --prefix /tmp/play-creator-rls --ignore-scripts @electric-sql/pglite
node scripts/check_rls.mjs /tmp/play-creator-rls/node_modules/@electric-sql/pglite/dist/index.js
```

`tests/fixtures/creator_rls_bootstrap.sql` is a minimal Auth-role fixture **only for an empty test database**. Never apply it to Supabase. The actual migration and `tests/creator_rls.sql` test owner CRUD, cross-user read/update/delete isolation, spoofed inserts, ownership transfer and anonymous denial. Live Supabase Auth/PostgREST still requires deployment credentials and project configuration.
