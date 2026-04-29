# Frontend

Vue 3 + Vite frontend for aonarr.

## Run locally

```powershell
npm install
npm run dev
```

Default URL:

```text
http://localhost:5173
```

## Production image

The Dockerfile builds the Vue app and serves it with Nginx on port 80.
The Nginx config serves the SPA and proxies `/api` requests to the backend service.
