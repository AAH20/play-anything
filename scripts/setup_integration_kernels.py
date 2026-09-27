"""Fetch reviewed kernel revisions; never execute downloaded source or overwrite a checkout."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENV_NAMES = {
    "graph-rag-np-hard-kernel": "GRAPH_RAG_KERNEL_PATH",
    "agentic-np-hard-kernel": "AGENTIC_KERNEL_PATH",
    "mirofish-swarm-optimizer": "MIROFISH_KERNEL_PATH",
    "agentic-graph-swarm-kernel": "GRAPH_SWARM_KERNEL_PATH",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-env", action="store_true", help="Add missing local configuration; preserve existing values")
    parser.add_argument("--check", action="store_true", help="Only report whether pinned checkouts are available")
    args = parser.parse_args()
    sources = json.loads((ROOT / "integrations/kernel-sources.json").read_text())
    destination = ROOT / ".integration-sources"
    manifest = destination / "sources.json"
    previous = {item["name"]: item for item in json.loads(manifest.read_text())} if manifest.exists() else {}
    installed = []
    for source in sources:
        name, revision = source["name"], source["revision"]
        if name not in ENV_NAMES or source["repository"] != f"https://github.com/AAH20/{name}":
            raise SystemExit("Kernel source manifest contains an unrecognized repository.")
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise SystemExit("Kernel revision must be an exact Git commit.")
        target = destination / name
        if target.exists():
            if (target / ".git").exists():
                found = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
            else:
                found = previous.get(name, {}).get("revision")
            if found != revision:
                raise SystemExit(f"Existing checkout has another/unknown revision: {target}; preserve or move it first.")
        elif args.check:
            raise SystemExit(f"Missing checkout: {name}. Run without --check to download it.")
        else:
            target.mkdir(parents=True)
            for command in (
                ["git", "init", str(target)],
                ["git", "-C", str(target), "remote", "add", "origin", source["repository"]],
                ["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision],
                ["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"],
            ):
                subprocess.run(command, check=True)
        installed.append({**source, "path": str(target)})
        print(f"{name}: {revision[:12]} available (no source executed)")
    if args.check:
        return
    destination.mkdir(exist_ok=True)
    manifest.write_text(json.dumps(installed, indent=2) + "\n")
    if args.write_env:
        env = ROOT / "apps/web/.env.local"
        existing = env.read_text() if env.exists() else ""
        keys = {line.split("=", 1)[0].strip() for line in existing.splitlines() if "=" in line and not line.lstrip().startswith("#")}
        additions = []
        if "INTEGRATION_ACCESS_TOKEN" not in keys:
            additions.append("INTEGRATION_ACCESS_TOKEN=" + secrets.token_urlsafe(32))
        for source in installed:
            key = ENV_NAMES[source["name"]]
            if key not in keys:
                additions.append(key + "=" + json.dumps(source["path"]))
        if additions:
            with env.open("a") as output:
                output.write("\n# Optional local kernel execution\n" + "\n".join(additions) + "\n")
            os.chmod(env, 0o600)
        print("Local environment configured; existing values preserved. Token values are not printed.")


if __name__ == "__main__":
    main()
