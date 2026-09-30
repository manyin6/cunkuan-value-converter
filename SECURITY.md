# Security

## Never commit secrets

Do **not** commit:

- `.admin_key` or any rotated production admin keys
- `.env` / `.env.*`
- `data/stats.json`, `data/visitors.json`, or any live analytics
- Private certificates / tokens

The included default `ADMIN_KEY` value (`deposit2026`) is a **local-preview convenience only**. Always set a strong random `ADMIN_KEY` via environment variable in production.

If a real key was ever committed or pasted into chat/docs: **rotate immediately**, deny old keys at the edge, and treat stats endpoints as compromised until rotated.

## Nginx path denials (required in production)

Do not let the static file server expose source or data. Example:

```nginx
location ~ /\.admin_key { deny all; return 404; }
location ^~ /data/ { deny all; return 404; }
location = /server.py { deny all; return 404; }
location ~ /\.(env|git) { deny all; return 404; }
```

Prefer proxying only needed routes to the app, and serving static assets from a dedicated root that does not include `server.py` / `data/`.

## CORS allowlist

`ALLOWED_ORIGINS` must list only your real HTTPS front-end origin(s). Do not use `*` for `/api/event`.

## Rate limits

In-process limits in `server.py` help on a single worker. For multi-worker / multi-host, enforce Nginx (or CDN) `limit_req` on `/api/event` and `/api/qr`. See [HARDENING.md](./HARDENING.md).

## Do not expose stats publicly

- `/admin` and `/api/stats` require `ADMIN_KEY`
- Do not link the admin URL in public pages
- Do not mirror `data/*.json` to object storage without access control

## Reporting

If you find a vulnerability in this repository, open a private security advisory or contact the maintainer via GitHub.
