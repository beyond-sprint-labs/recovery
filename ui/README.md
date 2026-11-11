# Recovery — Frontend (React + Vite + AG Grid Community)

Merchant console, customer portal and live audit trail for Recovery (PayPal AI Hackathon 2026).

## Stack
- React 18, TypeScript 5.5, Vite 5
- AG Grid Community 36.3.0 (no Enterprise modules)
- React Router 6, native `fetch` (single client in `src/api/client.ts`)

## Run locally
Requires Node 20+ and the FastAPI backend on `http://127.0.0.1:8000`.

```bash
cd ui
npm ci
npm run dev
```

The dev server proxies `/api` and `/health` to the backend, so no CORS setup is needed.
Set `VITE_API_URL` only when the API lives on a different origin.
Set `VITE_USE_MOCKS=true` to run against the bundled JSON mocks.

## Build
```bash
npm run build
```

## Security notes
- Money values stay strings end to end and are formatted without numeric conversion.
- The customer view renders only the contract fields of `CustomerProposalView`.
- Customer tokens are never written to browser storage.
- `npm audit --omit=dev` reports `react-router` advisories (open redirect on backslash links,
  SSR hydration). The app is a client-only SPA and navigates only to fixed internal routes.