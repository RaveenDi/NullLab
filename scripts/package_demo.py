"""Package read-only public evidence and architecture, with no fake workdesk API."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
dest = ROOT / "out/public-demo"
dest.mkdir(parents=True, exist_ok=True)
payloads = {}


def links(html):
    html = html.replace('href="/#method"', 'href="./architecture.html"')
    for before, after in (("/static/", "./static/"), ("/architecture", "./architecture.html"), ("/workdesk", "./workdesk-info.html"), ("/evidence", "./index.html")):
        html = html.replace(f'href="{before}', f'href="{after}').replace(f'src="{before}', f'src="{after}')
    return html.replace('href="/"', 'href="./index.html"')


html = links((ROOT / "app/static/evidence.html").read_text(encoding="utf-8"))
html, injected = re.subn(
    r'(<script\b[^>]*\bsrc="\./static/evidence\.js"[^>]*>)',
    lambda match: '<script src="./static/recording.js"></script>' + match[1],
    html, count=1,
)
if injected != 1:
    raise ValueError("The public evidence recording must load before the evidence client")
payloads["index.html"] = html.encode()
payloads["architecture.html"] = links((ROOT / "app/static/architecture.html").read_text(encoding="utf-8")).encode()
payloads["workdesk-info.html"] = b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local Research Workdesk - NullLab</title><link rel="stylesheet" href="./static/site.css"></head><body><main class="site-container"><p class="eyebrow">NULLLAB / RECORDED PUBLIC PACKAGE</p><h1>The Research Workdesk runs locally.</h1><p>This package contains recorded public evidence and an interactive explanation of the architecture. It does not run uploaded data, create investigations or call models.</p><p>Use the local NullLab application to bring your own question, attach materials and run an investigation. Follow its source README for setup; the local workdesk is at /workdesk.</p><a class="button primary" href="./index.html">Inspect recorded evidence</a><a class="button secondary" href="./architecture.html">Explore architecture</a></main></body></html>'''
for name in ("site.css", "site.js", "evidence.css", "evidence.js", "architecture.css", "architecture.js"):
    payloads["static/" + name] = (ROOT / "app/static" / name).read_bytes()
for path in (ROOT / "app/static/fonts").iterdir():
    if path.is_file():
        payloads["static/fonts/" + path.name] = path.read_bytes()
data = json.loads((ROOT / "examples/secom/results.json").read_text(encoding="utf-8"))
payloads["static/recording.js"] = ("window.__NL_PUBLIC_EVIDENCE = " + json.dumps(data, ensure_ascii=True) + ";\n").encode()
payloads["README.txt"] = b"Open index.html for recorded public evidence, or architecture.html for the explanatory model/execution flow. This package does not execute code, call models or offer a hosted workdesk. New investigations run in the local source application.\n"
manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}
payloads["manifest.json"] = json.dumps(manifest, indent=2).encode()
for name, data in payloads.items():
    path = dest / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
output = ROOT / "out/nulllab-public-demo.zip"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(payloads.items()):
        archive.writestr(name, data)
print(output)
