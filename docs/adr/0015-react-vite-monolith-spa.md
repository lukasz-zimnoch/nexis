# ADR-0015: React + Vite SPA Served from the FastAPI Container

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-10 |
| **Deciders** | Łukasz Zimnoch |

## Context

[ADR-0014](0014-firebase-auth-firestore-persistence.md) introduced Firebase
Auth and Firestore so the pipeline can be driven from a browser instead of
`curl` and a Google identity token. That decision implies a frontend, but it
does not say *which* frontend stack, *how* it is built, or *where* it is
served from. Three concrete questions need answers:

1. **Framework and tooling.** What renders the UI and bundles the assets?
2. **Hosting topology.** Does the SPA live in its own service (separate
   Cloud Run / Firebase Hosting / static bucket), or in the same container
   as the FastAPI backend?
3. **Build pipeline.** How does the SPA reach production without adding a
   second deployment workflow?

Constraints that shape the answer:

- Internal-only tool, single deployer, ~10 jobs/month. Operational simplicity
  matters more than scale or polish.
- One existing CI/CD pipeline (`build` + `deploy.yml`) targets a single
  Cloud Run Service from a single container image. Adding a parallel pipeline
  doubles the moving parts and the credentials surface.
- The backend is already a FastAPI app — serving a handful of static files
  from the same process is trivial (`StaticFiles` + a catch-all route).
- The SPA needs to call `/api/jobs` and pass a Firebase ID token. Same-origin
  hosting eliminates CORS configuration entirely.

## Decision

We adopt **React 18 + Vite 5 + TypeScript** for the SPA, and serve the built
assets from the same FastAPI container that hosts the API. There is no
separate frontend service.

Concretely:

- The SPA lives in `frontend/` with its own `package.json`, `tsconfig`, and
  `vite.config.ts`.
- A multi-stage `Dockerfile` builds the SPA in a `node:20-slim` stage, then
  copies `dist/` into `/app/frontend/dist/` of the Python runtime stage.
- `server.py` mounts `/assets` via `StaticFiles` and registers a catch-all
  route that returns `index.html` for any non-API path so the React Router
  client routing works on direct navigation and reload. The SPA mount is
  guarded by `if STATIC_DIR.is_dir()` so the backend is still runnable
  locally without a frontend build.
- Firebase Auth runs on the client via the Firebase JS SDK; the dashboard
  attaches `Authorization: Bearer <id_token>` to every API request via a
  shared `apiFetch` helper that calls `auth.currentUser.getIdToken()`.
- React Router 6 handles client-side routing. Three pages: `LoginPage`,
  `DashboardPage`, `JobDetailPage`. Polling (`setInterval`) drives status
  updates while jobs are pending or running.
- Tests use Vitest + React Testing Library, run as a separate CI job
  (`test-frontend`) alongside the existing Python test job.

## Considered Alternatives

### Option A: Next.js (App Router) on Cloud Run

Use Next.js as a full-stack React framework, deployed as its own service.

**Pros**
- Server components, built-in routing, image optimization, file-based API
  routes — a more "batteries included" experience.
- Built-in API route layer could replace some FastAPI endpoints.

**Cons**
- Two services to deploy: Next.js + FastAPI (the pipeline still needs the
  Python LangGraph runtime; we cannot port it to Node).
- Either CORS configuration (cross-origin calls between the two services) or
  a custom Next.js rewrite layer that proxies `/api` to the FastAPI service.
- Larger framework, larger attack surface, larger build, more decisions
  (App Router vs Pages Router, server vs client components, caching modes).
- The SPA does no SSR-worthy work — all rendering is gated behind login and
  dashboard data, so SSR adds latency without SEO or first-paint benefit.

### Option B: Firebase Hosting for the SPA + Cloud Run for the API

Deploy `dist/` to Firebase Hosting, keep FastAPI on Cloud Run.

**Pros**
- Firebase Hosting has a generous free tier and a global CDN.
- The frontend deploy decouples from the backend deploy, so a UI tweak does
  not rebuild the Python image.
- Naturally co-located with Firebase Auth in the GCP console.

**Cons**
- A second deploy pipeline (or a second job in the existing one) to manage
  Firebase Hosting credentials, channels, and previews.
- Cross-origin calls from `nexis.web.app` to `nexis-xyz.run.app` require
  CORS configuration on the FastAPI side and complicate Firebase Auth's
  ID-token cookie behavior in production.
- For ~10 jobs/month, the CDN and decoupled-deploy benefits are dead weight.

### Option C: GCS bucket + load balancer for the SPA

Upload the build to a GCS bucket fronted by an HTTPS load balancer that
also routes `/api/*` to Cloud Run.

**Pros**
- Cheapest possible hosting for static files.
- Single hostname for SPA + API, no CORS.

**Cons**
- A global HTTPS load balancer is the most operationally heavy option of
  the three: forwarding rules, backend buckets, URL maps, SSL certs.
- LB minimum cost (~$18/month for the forwarding rule) is more than the
  rest of the stack combined.
- Adds Terraform surface area we do not need yet.

### Option D: SvelteKit / SolidStart / other meta-framework

Use one of the lighter React alternatives.

**Pros**
- Smaller bundle, faster runtime, less ceremony.

**Cons**
- Smaller ecosystem; the Firebase JS SDK is React-first in its docs and
  examples.
- Author and any future contributors are more familiar with React.
- The frontend is small enough that framework choice is not the bottleneck.

### Option E: Plain JavaScript (no framework)

Hand-rolled vanilla JS + a templating library.

**Pros**
- Zero framework dependencies, smallest possible bundle.

**Cons**
- Auth state management, polling, routing, form state — all of these need
  to be reimplemented or stitched together from micro-libraries.
- Slower to build and harder to evolve than a 200-line React app.

## Consequences

### Positive

- **One image, one deploy.** The existing `deploy.yml` pushes a single
  container image to Cloud Run; the SPA goes along for the ride. No new
  credentials, no new pipeline, no version skew between API and UI.
- **No CORS.** Same-origin requests from the SPA to `/api/jobs` mean the
  FastAPI app needs zero CORS middleware, and Firebase Auth's ID token
  flow has no cross-site cookie pitfalls.
- **Vite dev experience.** `npm run dev` provides HMR with a proxy to the
  local FastAPI server; the backend can be developed in isolation by
  hitting `/api` directly.
- **Build is cacheable.** The multi-stage Dockerfile copies
  `frontend/package.json` + `package-lock.json` first so an unchanged
  dependency tree skips `npm ci` on rebuilds.

### Negative

- **Coupled deploy cadence.** A frontend-only change still rebuilds the
  Python image and redeploys the Cloud Run Service. Acceptable for ~1
  deploy/week; would be a problem at higher frequency.
- **No CDN.** Static assets are served by the same Cloud Run Service that
  serves the API. Cold-start latency on the first request is noticeable
  (~1-2s), but the dashboard is internal-only and not latency-sensitive.
- **Bundle size visible to users.** The Firebase JS SDK + React + react-markdown
  comes to ~125 KB gzipped. Acceptable for an internal tool; would warrant
  code-splitting for a public app.

### Trade-offs

- We accept tighter coupling between the SPA and the API (one image, one
  deploy) in exchange for one less service to operate. If frontend deploys
  ever need to ship independently of backend deploys, splitting the SPA off
  to Firebase Hosting (Option B) is a non-destructive migration: drop the
  static-file mount from `server.py`, point CI at `firebase deploy` for
  the `frontend/dist/` artifact, and add CORS to the FastAPI app.
- We accept React over a smaller framework because the auth + polling +
  routing combo benefits more from React's ecosystem than from any single
  framework's runtime efficiency. Bundle size is not on the critical path
  for an internal tool.
