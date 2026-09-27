# Graph Studio

Optional Next.js interface for Play Anything. Requires Node.js 20.9+ and Python 3.10+ for preparing repository assets.

From the repository root:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Open http://127.0.0.1:3000. Local graph exploration and deterministic specialist analysis require no provider credentials.

See [configuration, capabilities and constraints](../../docs/nextjs-graph-studio.md) for optional model-team orchestration, Neo4j storage, Creator integration and deployment boundaries. Copy `.env.example` to `.env.local` only when enabling an optional backend; never commit secrets.

```sh
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```
