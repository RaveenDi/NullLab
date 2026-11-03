"""Job-scoped compatible chat provider, explicit replay and durable budget reservations.

No client or credentials are global. Construction never makes a request. Completed
responses record actual token usage; reservations for unknown-billed attempts are
retained conservatively. A deadline cannot cancel remote inference.
"""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import threading
import time
from collections.abc import Callable
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ProviderError(RuntimeError):
    pass


class BudgetExceeded(ProviderError):
    pass


def _local(host: str | None) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def read_config(env_file: str | Path | None = ".env") -> dict[str, str]:
    """Read literal KEY=value entries; process environment takes precedence.

    Never execute shell substitutions, expand variables or mutate os.environ.
    """
    values = {}
    if env_file and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and key.replace("_", "").isalnum() and not key[0].isdigit():
                if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key] = value
    values.update(os.environ)
    return values


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str = "https://api.meta.ai/v1"
    api_key: str = field(default="", repr=False)
    model: str = "muse-spark-1.3"
    role_models: dict[str, str] = field(default_factory=dict)
    reasoning_effort: str | None = "low"
    max_tokens: int = 12000
    timeout_s: float = 90.0
    retries: int = 1

    def __post_init__(self):
        u = urllib.parse.urlsplit(self.base_url)
        if u.username or u.password or u.query or u.fragment or not u.hostname:
            raise ProviderError("provider URL must contain only scheme, host, port and path")
        if u.scheme != "https" and not (u.scheme == "http" and _local(u.hostname)):
            raise ProviderError("remote inference requires HTTPS; HTTP is allowed only on loopback")
        if not (0 < self.max_tokens <= 128000) or not (0 < self.timeout_s <= 600) or not (0 <= self.retries <= 3):
            raise ProviderError("invalid provider token, timeout or retry limits")

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> ProviderConfig:
        e = read_config(env_file)
        base = e.get("MODEL_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
        meta = urllib.parse.urlsplit(base).hostname == "api.meta.ai"
        roles = {k[len("NULLLAB_MODEL_") :].lower(): v for k, v in e.items() if k.startswith("NULLLAB_MODEL_") and v}
        if meta:
            roles.setdefault("critic", "muse-wonder-1.0")
        effort = e.get("NULLLAB_REASONING_EFFORT", "low" if meta else "") or None
        return cls(
            base_url=base,
            api_key=e.get("MODEL_API_KEY", ""),
            model=e.get("NULLLAB_MODEL", "muse-spark-1.3" if meta else "local"),
            role_models=roles,
            reasoning_effort=effort,
            max_tokens=int(e.get("NULLLAB_MAX_TOKENS", "12000" if meta else "4096")),
            timeout_s=float(e.get("NULLLAB_TIMEOUT_S", "90")),
            retries=int(e.get("NULLLAB_RETRIES", "1")),
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("provider redirects are refused")


def _request(config: ProviderConfig, payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = "Bearer " + config.api_key
    req = urllib.request.Request(
        config.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.build_opener(_NoRedirect()).open(req, timeout=config.timeout_s) as r:
        raw = r.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ProviderError("provider response exceeds 8 MiB")
    return json.loads(raw)


class Provider:
    def __init__(
        self,
        config: ProviderConfig,
        job_dir: str | Path,
        max_usd: float = 1.0,
        max_calls: int = 4,
        replay_path: str | Path | None = None,
        transport: Callable[[ProviderConfig, dict], dict] | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ):
        if (
            not math.isfinite(max_usd)
            or max_usd < 0
            or isinstance(max_calls, bool)
            or not isinstance(max_calls, int)
            or max_calls < 0
        ):
            raise ProviderError("budgets must be nonnegative")
        self.config = config
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.job_dir / "provider-ledger.json"
        self.max_usd, self.max_calls = float(max_usd), int(max_calls)
        self.transport = transport or _request
        self.cancelled = cancelled
        self._replay_lock = threading.Lock()
        self._replay = None
        if replay_path is not None:
            self._replay = defaultdict(deque)
            for line in Path(replay_path).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._replay[row["key"]].append(row["reply"])

    def model_for(self, role: str) -> str:
        return self.config.role_models.get(role, self.config.model)

    @property
    def is_replay(self) -> bool:
        return self._replay is not None

    @contextmanager
    def _locked(self):
        # mkdir is atomic across threads/processes sharing this job workspace.
        lock = self.job_dir / ".provider-lock"
        end = time.monotonic() + 3
        while True:
            try:
                lock.mkdir()
                break
            except FileExistsError:
                if time.monotonic() >= end:
                    raise ProviderError("provider ledger busy; lock recovery requires inspection") from None
                time.sleep(0.01)
        try:
            yield
        finally:
            lock.rmdir()

    def _read(self):
        if not self.state_path.exists():
            return {"version": 1, "attempts": []}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, state):
        tmp = self.job_dir / (".ledger-" + uuid.uuid4().hex + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _reserve(self, role, model, key, estimate):
        with self._locked():
            state = self._read()
            live = [r for r in state["attempts"] if not r.get("replayed")]
            if len(live) >= self.max_calls or sum(r["reserved_usd"] for r in live) + estimate > self.max_usd + 1e-12:
                raise BudgetExceeded("job inference budget exhausted")
            row = {
                "id": uuid.uuid4().hex,
                "role": role,
                "model": model,
                "prompt_key": key,
                "status": "attempted",
                "reserved_usd": estimate,
                "usage": {},
                "billing": "unknown",
                "started_unix": time.time(),
                "replayed": False,
            }
            state["attempts"].append(row)
            self._write(state)
            return row["id"]

    def _finish(self, attempt, **fields):
        with self._locked():
            state = self._read()
            row = next(r for r in state["attempts"] if r["id"] == attempt)
            row.update(fields, finished_unix=time.time())
            self._write(state)

    def ledger(self):
        with self._locked():
            state = self._read()
        live = [r for r in state["attempts"] if not r.get("replayed")]
        return {
            "calls": len(live),
            "replayed_calls": len(state["attempts"]) - len(live),
            "est_usd": round(sum(r["reserved_usd"] for r in live), 6),
            "usage": {
                k: sum(r.get("usage", {}).get(k, 0) or 0 for r in live)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "detail": state["attempts"],
            "note": "Reserved estimates, not billing. Unknown-billed attempts retain their reservation.",
        }

    def _estimate(self, model, payload):
        # Conservative input upper bound: UTF-8 bytes, and full output budget.
        # Pricing is an estimate and intentionally retained even after failures.
        host = urllib.parse.urlsplit(self.config.base_url).hostname
        if _local(host):
            return 0.0
        inp, out = (4.0, 20.0) if "wonder" in model else ((0.10, 0.20) if "contributor" in model else (1.25, 4.25))
        return (len(json.dumps(payload).encode()) * inp + self.config.max_tokens * out) / 1_000_000

    def complete(self, system: str, user: str, role: str = "planner", response_format: dict | None = None) -> str:
        model = self.model_for(role)
        payload = {
            "model": model,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort
        if response_format:
            payload["response_format"] = response_format
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if self._replay is not None:
            with self._replay_lock:
                if not self._replay[key]:
                    raise ProviderError("replay miss or exhausted reply sequence")
                reply = self._replay[key].popleft()
            with self._locked():
                state = self._read()
                state["attempts"].append(
                    {
                        "id": uuid.uuid4().hex,
                        "role": role,
                        "model": model,
                        "prompt_key": key,
                        "replayed": True,
                        "status": "completed",
                        "reserved_usd": 0.0,
                        "usage": {},
                    }
                )
                self._write(state)
            return reply
        if not self.config.api_key and not _local(urllib.parse.urlsplit(self.config.base_url).hostname):
            raise ProviderError("MODEL_API_KEY is required for remote inference")
        estimate = self._estimate(model, payload)
        for index in range(self.config.retries + 1):
            if self.cancelled():
                raise ProviderError("cancelled before provider attempt")
            attempt = self._reserve(role, model, key, estimate)
            q = queue.Queue(maxsize=1)

            def work(output=q):
                try:
                    output.put((True, self.transport(self.config, payload)))
                except Exception as error:
                    output.put((False, error))

            threading.Thread(target=work, daemon=True).start()
            try:
                ok, data = q.get(timeout=self.config.timeout_s)
            except queue.Empty:
                self._finish(attempt, status="timeout", error="deadline exceeded; remote cancellation unconfirmed")
                # Do not retry an abandoned request that may still be billed.
                raise ProviderError("provider deadline exceeded; billing unknown") from None
            if not ok:
                code = data.code if isinstance(data, urllib.error.HTTPError) else None
                self._finish(attempt, status="failed", error_type=type(data).__name__, http_status=code)
                if code in {429, 502, 503, 504} and index < self.config.retries:
                    time.sleep(min(0.5 * 2**index, 2))
                    continue
                # Do not include exception/body text: it may contain credentials or private input.
                raise ProviderError(f"provider request failed ({type(data).__name__})") from None
            try:
                reply = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError("empty response")
                usage = {
                    k: int(usage[k])
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if isinstance(usage.get(k), (int, float)) and usage[k] >= 0
                }
            except (KeyError, IndexError, TypeError, ValueError):
                self._finish(attempt, status="invalid_response")
                raise ProviderError("provider returned malformed or empty content") from None
            self._finish(attempt, status="completed", usage=usage, billing="usage_received" if usage else "unknown")
            # Traces hold prompt identity and reply, not credentials or prompt contents.
            with self._locked(), (self.job_dir / "provider-traces.jsonl").open("a", encoding="utf-8") as trace:
                trace.write(json.dumps({"key": key, "reply": reply, "model": model, "role": role}) + "\n")
            return reply
        raise ProviderError("request retries exhausted")
