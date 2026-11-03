# Supported deployment

Use Python 3.12 and run `python -m uvicorn app.server:app --host 127.0.0.1 --port 8099`. Keep the service local. It is a local author workspace with trusted cases and data-only generated pipelines, not a public arbitrary-code service.

Copy `.env.example` to `.env` for hosted inference, or configure a compatible loopback model server. `MODEL_BASE_URL`, `NULLLAB_MODEL`, role models and timeouts are read by the v2 provider. No secret is required for the rules path or an unauthenticated loopback model server. Web live inference additionally requires `NULLLAB_ALLOW_WEB_LIVE=1` in the server environment, plus the user's outbound-data acknowledgement in the UI.

Job directories live under ignored `out/jobs/`, with UUIDs, atomic JSON state and separate ledgers. A restarted server marks interrupted jobs failed; start a new run. Queue capacity is four and active workers two. Cancellation is cooperative and may wait for the current bounded stage. Do not assume a timeout cancels provider billing.

The local workspace lists saved audits and supports reopening by `?job=UUID`. Generated case revisions preserve CSV bytes and old outcomes, adding parent hashes and declarations for a new audit. Keep `examples/user-*`, job directories and intake staging private. The public view-only package disables intake, revisions, job recovery and inference; it displays only explicitly selected public recordings. Unmeasured assessments and measured bundles both include input source/data and require review before sharing.

A public demo should serve only explicitly public recordings, with execution disabled, until a verified hosted isolation/access/budget design exists. No production URL, account authentication, general hosted sandbox, Glimmer deployment or uptime guarantee has been validated by this rebuild. Submission deployment and final video remain explicit release deliverables.
