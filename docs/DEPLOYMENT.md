# NullLab deployment runbook

Written 2026-11-02. This is an engineering runbook: which deployment shapes are supported, the rules every deployment follows, and a pre-deploy checklist. Read [SECURITY.md](SECURITY.md) first; the security model sets most of the limits here. Anything marked **UNVERIFIED** has not been tested on this project.

**Status of the paths**

| Path | Status |
|---|---|
| (a) Local CLI | Supported. Tested on Windows with Python 3.12 |
| (b) GitHub Action, rules only | Written, checked locally, **never run on GitHub: UNVERIFIED** |
| (c) Container | `Dockerfile` exists, **never built or run: UNVERIFIED** |
| (d) Hosted demo, static replay page | Supported shape; the page is self-contained |
| (e) Hosted audit service | **Not recommended** until a container boundary is verified |

---

## 1. Deployment options

### (a) Local / CLI

The reference deployment. One user, one machine, their own cases.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m agent.hybrid <case_dir> --out out/hy --report out/hy.md
```

- Offline by default: no model call, no network, $0. `--live` enables model calls and still passes the spend check and call caps in `agent/llm.py`; if the spend-check tooling is absent the call is refused (fail closed).
- Set `NULLLAB_SANDBOX_REQUIRE_LIMITS=1` so the run stops if the Windows Job Object or POSIX limits cannot be applied, instead of running unlimited.
- Set `NULLLAB_NO_DOCKER=1` while the Docker path is unverified, so the single-experiment path never selects it automatically when Docker happens to be installed.
- POSIX resource limits (`RLIMIT_AS`, `RLIMIT_NPROC`) are written but **UNVERIFIED** on Linux and macOS.
- The local server (`python -m uvicorn app.server:app --port 8099`) has no authentication or rate limiting. Bind it to 127.0.0.1 only.

### (b) GitHub Action, rules only

`.github/workflows/nulllab-audit.yml` runs `agent.ci_check` on pull requests and pushes: rules only, no model, no secrets, `permissions: contents: read`, 30-minute timeout. `.github/workflows/ci.yml` runs lint, `scripts/freeze_check.py verify --allow-missing-data` and the offline tests.

- Exit codes: 0 nothing above the threshold, 1 a case INFLATED beyond it (95% interval above 0), 2 nothing audited or a measurement failed. A case where no rule fired is reported as not checked, exit 0. Do not read exit 0 as "clean".
- The job executes the `train.py` of every case under `AUDIT_PATH`. On a public repository, a pull request from a fork can change that code. Keep the trigger as `pull_request` (not `pull_request_target`), keep `permissions: contents: read`, and never add a secret to this job.
- Spark mode (`--spark --live`) is **not** enabled in the workflow. It needs `MODEL_API_KEY` as a repository secret and depends on the owner's spend-gate tooling, which is not present on a stock runner: **UNVERIFIED**. Do not enable it on a public repository where forks can trigger runs.
- **UNVERIFIED:** neither workflow has run on GitHub. Verify on a branch before relying on the status check.

### (c) Container

The `Dockerfile` pins `python:3.12-slim`, scikit-learn 1.9.1, pandas 3.1.0 and numpy 2.5.4 and switches to a non-root user. `sandbox/executor.py` has a Docker backend (`--network=none --read-only --memory=6g --pids-limit=64 --tmpfs /tmp`). **Neither has been built or run: UNVERIFIED.** Do not rely on it until it passes the hostile-code tests in `tests/test_sandbox_hardening.py` inside the container.

Hardened spec for a container worker (one container per audit job):

| Control | Setting |
|---|---|
| Network | `--network=none`. The worker never needs the network; model calls happen outside the worker |
| Filesystem | `--read-only` root; one `--tmpfs` work directory with a size cap (for example `--tmpfs /work:rw,size=512m,noexec`); case files copied in, truth files never mounted |
| Memory | `--memory` and `--memory-swap` equal (for example 6g), so no swap |
| Processes | `--pids-limit` (64 or lower) |
| CPU | `--cpus` (for example 2) plus the existing wall-clock timeout |
| User | non-root (`USER runner` in the Dockerfile); `--user` with a fixed uid |
| Privileges | `--cap-drop=ALL`, `--security-opt no-new-privileges`, default seccomp profile, no `--privileged`, no host mounts beyond the work dir |
| Environment | No secrets. Pass only `PYTHONHASHSEED`, `OMP_NUM_THREADS` and limit settings |
| Lifetime | `--rm`; one job per container; container destroyed after the job |
| Multi-tenant | Containers share the host kernel. For code from more than one tenant, run each job under gVisor (`runsc`) or in a Firecracker microVM, on hosts that hold no secrets |
| Image | Build from a pinned base digest; rebuild on dependency updates; scan the image; keep wheels vendored for offline rebuilds |

### (d) Hosted demo: static replay-only page

The demo page `report/index.html` is one self-contained file (HTML, inline CSS and JS, embedded run data, no external requests). Build it with `python -m report.render` and host the `report/` folder on any static host.

- No model calls, no user code, no server-side execution, no keys.
- Host the static files, not `app/server.py`. The server's `POST /api/run/{case}` runs a repository case through the sandbox (mock mode, live refused); a public host should not execute code on request.
- Rebuild the page from run files for each release; never hand-edit numbers in the HTML.
- Keep it up for the judging window (Nov 5 to 8, 2026) and check the URL from a private browser window.

### (e) Hosted audit service: not recommended

A service that accepts a user's `train.py` and data would run untrusted code. The current sandbox is a restricted subprocess with a Python audit hook, which native code can bypass. Do not offer this until all of the following are true:

1. The container or microVM worker in (c) is built, passes the hostile-code tests inside the boundary, and runs on hosts with no secrets.
2. The API process and the worker are separate; the API never imports or executes user code.
3. Authentication, per-user rate limits, per-run spend ceilings and quotas are in place.
4. Model calls use the standard (non-Contributor) model for user data, or the user consents to the Contributor terms in writing.
5. Retention and deletion of uploaded code and data are defined and enforced.

---

## 2. Rules for every deployment

1. **Never run untrusted code in-process on a shared host.** The audited pipeline runs only in the sandbox worker, and only on a host where a breakout exposes nothing of value. The CI check and the audit execute case code: do not point them at code you do not trust.
2. **API keys only via environment or a secret store.** `MODEL_API_KEY` comes from the environment or a local `.env` (gitignored; template in `.env.example`). Never in an image, a layer, the repository, a log, a bundle, a screenshot or the video. The sandbox environment is scrubbed so the key is not inherited; bundles are scanned and key-shaped strings redacted, and the build is refused if one remains.
3. **Per-run spend ceiling and spend gate.** Every live call passes the per-phase call cap and the spend check before the request, and each attempt is logged before it is sent. Set a ceiling per run and a spend alert on the Meta billing page. Live mode is CLI only; the web server refuses it.
4. **Contributor model data terms.** `muse-spark-1.3-contributor` may use submitted data for training. Send it only public or disguised data. Prompts contain `train.py`, the excerpt and a limited description of the data; check the prompt builders before using private material.
5. **Rate limits.** Respect the Meta Model API limits (Contributor 150 RPM, standard Spark 3,000 RPM, per the Meta Model API documentation). Use the transport deadlines and retries in `agent/transport.py`; count a timeout as a harness failure, never re-roll it silently.
6. **Run ids and traces.** Every run writes a run id, the prompts and replies, the call log and the score file. Keep them with the result they produced; a number without its run file is not published.
7. **Retention.** Keep evidence runs (`runs_*/`) for the life of the project; they are the record behind every published number. Delete scratch output (`out/`, temp dirs) after use; the sandbox already deletes its work directory. For any hosted service, delete uploaded code and data after the job unless the user opts in, and state the period.
8. **Release gate.** Before a release or tag: the full offline test suite passes (`python -m pytest -m "not slow and not live" -q`, and the slow tests before a tagged release); `python scripts/freeze_check.py verify` passes; the frozen-evidence tags still point at their commits (`g9-run-2026-11-02`, `g9b-run-2026-11-02`); `python -m report.render` rebuilds the page with no number change you cannot trace to a run file.
9. **Versioning and tags.** Tag each evidence run when it completes (`<run>-run-<date>`) and never move a tag. Product releases use their own version tags. A change to a frozen file needs an entry in `docs/FROZEN-CHANGELOG.json`; never regenerate the manifest to hide a change.
10. **Rollback.** Static demo: redeploy the previous build of `report/`. CLI and Action: pin users to the previous tag. Evidence is never rolled back or rewritten; a wrong result is corrected by a new, labelled run and a note beside the old one.
11. **Observability.** Log per run: run id, case, rule or model path taken, number of calls, estimated tokens and USD (the cost ledger), sandbox status and limit hits, elapsed time, verdict. Alert on spend near the ceiling, repeated sandbox limit hits and any `INCONCLUSIVE` spike.
12. **Incident response.** For a suspected key leak: revoke the key at the provider, rotate, search the repository history and published artifacts, and record the incident. For a suspected sandbox escape: stop all runs, keep the `train.py` and patch that triggered it, report privately as described in [SECURITY.md](SECURITY.md), and do not resume hosted execution until the cause is fixed and covered by a test. For a wrong published number: correct it in place with a dated note and keep the old value visible.
13. **Licence and data terms.** Code and docs are MIT ([LICENSE](../LICENSE)). The EHG cases derive from PhysioNet TPEHGDB under ODC-By 1.0; the attribution is in [NOTICE](../NOTICE) and must ship with any redistribution. The raw civil-war data behind the headline case is not redistributed; it is rebuilt locally by script with a checksum, and `data.csv` stays gitignored. Do not vendor code from repositories without a licence.

---

## 3. Hackathon rules that bind a public deployment

From the event rules (verified 2026-10-28 against the participant guide and official rules):

| Rule | Reference | What it means here |
|---|---|---|
| Repositories must be public | R1 | The repository and the demo URL must open in a private browser window |
| Judges must be able to tell what was created during the event, or risk disqualification | R3 | The README and video separate project code from third-party libraries and APIs |
| No code, data or assets without rights | R7 | Every dataset, image and font is licensed and credited in NOTICE |
| Broad licence to Meta, Cerebral Valley and partners | Official rules, IP section | Anything published can be used, reproduced and displayed by them |
| Nothing is confidential; no secrets, keys or private data in the repo, video or Discord | Official rules, IP section | Rule 2 above, applied to history, screenshots and recordings |
| The submission must be original work you own; open source allowed if licences are followed | Official rules, IP section | Dependencies installed from PyPI under their own licences, not vendored |
| Checklist: repo public, every asset licensed and credited, no keys in history | Submission checklist | Part of the pre-deploy checklist below |

---

## 4. Pre-deploy checklist

- [ ] `python -m pytest -m "not slow and not live" -q` passes (and the slow tests for a tagged release)
- [ ] `python scripts/freeze_check.py verify` passes
- [ ] Tags `g9-run-2026-11-02` and `g9b-run-2026-11-02` unchanged
- [ ] `python -m report.render` run; every number on the page traced to a run file
- [ ] No key in the working tree or history (search `git log -p` for `MODEL_API_KEY`, `sk-`, `Bearer`); `.env` is gitignored; `.env.example` holds no value
- [ ] No raw data from the headline case tracked; `real/*/data.csv` gitignored
- [ ] NOTICE carries the PhysioNet ODC-By attribution
- [ ] Static demo hosted as files only; no server executing code; URL checked in a private window
- [ ] `app/server.py`, if run at all, bound to 127.0.0.1
- [ ] `NULLLAB_NO_DOCKER=1` and `NULLLAB_SANDBOX_REQUIRE_LIMITS=1` set wherever the sandbox runs
- [ ] GitHub workflows: `permissions: contents: read`, no secrets, `pull_request` trigger only; first run checked on a branch
- [ ] Spend alert set on the Meta billing page; per-run ceiling set before any live run
- [ ] Contributor model used only with public or disguised data
- [ ] UNVERIFIED items still listed as UNVERIFIED in the README: Docker build, GitHub Actions run, POSIX limits, live Wonder referee
