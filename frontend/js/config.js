// Local-dev default. When deploying to GitHub Pages, .github/workflows/deploy.yml
// overwrites this file with the real Render backend URL from the
// BACKEND_API_URL repository variable, before the frontend/ artifact is
// uploaded — see that workflow for the generation step.
//
// This file is deliberately NOT the thing that silently ships a
// localhost URL to production: if BACKEND_API_URL is unset when a
// deploy runs, the workflow fails the build instead of publishing a
// broken site (see deploy.yml's "Guard: BACKEND_API_URL must be set" step).
window.KASI_API_BASE = window.KASI_API_BASE || 'http://localhost:8000';
