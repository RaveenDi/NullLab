# Deployment

NullLab is a local, single-operator service. It binds to loopback, rejects non-loopback clients and hosts, and runs trusted Python from the operator's own machine. Do not expose it to a network or host untrusted uploads with this build.

## Run locally

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt   # Windows: .venv\Scripts\python
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8099
```

## Model provider configuration

Copy `.env.example` to `.env` (gitignored) or set the same variables in the process environment. No key ships with the repository.

| Variable | Purpose |
|---|---|
| `MODEL_BASE_URL` | OpenAI-compatible chat endpoint (default `https://api.meta.ai/v1`) |
| `MODEL_API_KEY` | Your own key. May be blank for a loopback server |
| `NULLLAB_MODEL` / `NULLLAB_MODEL_CRITIC` | Planner and critic model IDs |
| `NULLLAB_ALLOW_WEB_LIVE=1` | Server-side opt-in so the web UI may make live model calls |

The default rules mode needs no key and makes no model calls.

## Static evidence demo

`python scripts/package_demo.py` builds `out/nulllab-public-demo.zip`, a read-only bundle of recorded evidence and UI assets (no uploads, no audits, no model calls). It can be served from any static host.

## Hosted audits

A public service that runs fresh audits is not provided. It would need authentication, per-user state, quotas and an isolated execution environment (for example one container task per audit), with provider credentials kept out of execution workers. The `Dockerfile` is a sandbox image, not a verified web-service image.
