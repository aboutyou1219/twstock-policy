# Web Development Workflow

This workflow keeps the Next.js development server and production build from writing to the same `.next` directory at the same time.

## Local Development

Run the web app from the web workspace:

```bash
cd web
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Build Verification

Use this as the minimum verification command before reviewing or shipping web changes:

```bash
cd web
npm run build
```

`npm run build` runs `scripts/guard-next-build.mjs` before `next build`. The guard refuses to build if `next dev` is active in the same `web` directory, because both commands write to `.next`.

If the guard blocks a build:

1. Stop the dev server.
2. Rerun `npm run build`.
3. Restart the dev server after the build completes.
