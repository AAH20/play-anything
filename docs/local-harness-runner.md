# Optional local harness runner

`integrations/harness_runner.py` is a separately started, loopback-only sidecar for running a small set of operator-approved CLI profiles. It is opt-in: the app does not launch it, no profile is enabled by the example, and no API or subscription credentials are copied from the browser into a child process. The CLIs use whatever account or provider configuration is already installed for the local user.

## Configure and start deliberately

1. Copy `integrations/harness-profiles.example.json` to a private file such as `integrations/harness-profiles.json`. Replace each trusted `workspace` with an absolute directory path. Keep all entries disabled until each command, authentication mode, workspace, and the CLI's own permission policy have been reviewed. Remove profiles you will not use. Never commit the private profile file.
2. Generate a local bearer secret, then configure the same value for the web app's `LOCAL_RUNNER_ACCESS_TOKEN` and this process:

   ```sh
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
   ```

   Use the printed value in your private local environment configuration. The runner rejects tokens shorter than 32 characters when started.
3. Start the bridge manually from the repository root:

   ```sh
   LOCAL_RUNNER_ACCESS_TOKEN='your-generated-local-secret' \
     python3 integrations/harness_runner.py --profiles /absolute/path/to/harness-profiles.json
   ```

   It binds only to `127.0.0.1:8765`. The web app should point `LOCAL_RUNNER_URL` at the base origin `http://127.0.0.1:8765`, with the matching token. Stop the runner with Ctrl-C. The example profile file is not a live config file.

The API requires a matching bearer token and a loopback client/Host/Origin. `GET /health` is unauthenticated on loopback and returns only bridge mode, active count, and number of explicitly enabled profiles. `POST /run` accepts at most 16 KiB of JSON. The server validates a server-generated UUID, supported integration/harness/auth mode, operation and bounded goal. The requested `(integrationId, harnessId, authMode)` must exactly match one enabled trusted profile, and its operation must match as well. No request field can choose a command, argument, working directory, environment, or executable path. The `graph` field is bounded metadata (`name`, `nodes`, `edges`) only; no graph contents are passed to the CLI.

The profile file pins the executable argv and working directory. `{prompt}` must occur exactly once as a standalone argument and is replaced by one bounded prompt argument; commands run with `shell=False`, closed stdin, and a new process group. The optional profile-owned `/understand` prefix is accepted only for an `understand-anything` entry. Installed commands inherit the local runner process environment and their own user-level authentication configuration; HTTP requests cannot add environment variables. Known values from secret-named environment variables and the runner bearer token are redacted from captured output. Do not start this process in an environment whose inherited variables or local CLI credentials you would not permit the configured harness to use.

At most two processes may run at once. A process is terminated as a process group on DELETE, after 40 seconds, or when the combined stdout/stderr exceeds 1 MiB. Successful POST responses contain `{status, workspace, profile, output, exitCode, usage: null}`. Failed, timed-out, output-limited, or cancelled runs use non-2xx responses with a bounded generic error; a failed run can include its redacted, size-bounded output and exit code. DELETE `/run/{requestId}` returns `202` when cancellation starts. The runner does not implement durable queues, retries, or billed-provider usage metering.

## Example profiles

The checked-in example file includes disabled templates for:

- Codex `exec` with `--sandbox read-only`; there is no `--yolo`/approval bypass.
- Claude Code restricted print/plan mode with only the `Read`, `Glob`, and `Grep` tools exposed. `--restricted` requires a recent CLI release; check the installed command's help and authentication behavior.
- Cursor's `cursor-agent --print` headless path. Cursor documents Ask as a read-only IDE mode but does not document an Ask mode flag for its CLI. Print mode can expose tools and its permissions depend on local CLI policy, so keep this profile disabled until you verify a local read-only policy; the example does not claim the CLI runs in Ask mode.
- OpenCode `run --agent plan`; configure and review a plan agent before enabling it.
- Hermes one-shot `hermes chat -q --oneshot`.
- OpenManus `python main.py --prompt`; its profile workspace must be a trusted OpenManus checkout containing `main.py`.
- UnderstandAnything through an installed host `/understand` plugin, illustrated with Codex read-only execution. The plugin must already be installed in that CLI's trusted host configuration.

These are templates, not proof that a CLI/version is installed or logged in. Test a disabled profile manually with a non-billed fixture first, inspect the command against the installed CLI's current documentation, then enable only the exact profile you reviewed. Subscription and API modes are separate explicit profile keys; the runner does not translate one into the other. There is no Antigravity CLI profile because a safe, supported headless command was not verified. Configure a separately reviewed adapter before adding one.

Current command references: [Codex CLI getting started](https://help.openai.com/en/articles/11096431-api-codex-cli-and-sign-in-with-chatgpt) and [Codex read-only sandbox policy](https://github.com/openai/codex/blob/main/codex-rs/prompts/templates/permissions/sandbox_mode/read_only.md); [Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage); [Cursor CLI parameters](https://docs.cursor.com/en/cli/reference/parameters), [headless usage](https://docs.cursor.com/en/cli/headless), and [Cursor modes](https://docs.cursor.com/agent); [OpenCode CLI](https://opencode.ai/v2/docs/cli) and [commands](https://opencode.ai/v2/docs/cli/commands); [Hermes CLI commands](https://hermes-agent.nousresearch.com/docs/reference/cli-commands); [OpenManus `main.py`](https://github.com/FoundationAgents/OpenManus/blob/main/main.py). Checked 2026-09-27. CLI flags and product behavior can change; the installed binary remains authoritative.

## Limits and security

The bridge is a local convenience layer, not a sandbox. A trusted profile can give its CLI filesystem or network access according to that CLI's own policy. Keep the workspace narrow, use each harness's restrictive mode, protect the bearer secret, and leave unneeded profiles disabled. The bridge starts no browser, accepts no remote bind address, and never executes raw client commands or Cypher. OpenManus and plugin profiles are particularly dependent on the locally installed version and workspace setup. No real paid harness was invoked as part of implementation tests.
