"""Evaluator-only: de-identify column names (stable salted hash). Never imported by agent/."""
import hashlib

SALT = "nulllab-v1"


def hname(name: str) -> str:
    return "c_" + hashlib.sha1((SALT + name).encode()).hexdigest()[:6]
