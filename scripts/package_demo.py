"""Create a portable view-only demo from public recorded evidence. No hosting action."""

from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
dest = ROOT / "out" / "public-demo"
dest.mkdir(parents=True, exist_ok=True)
(dest / "static").mkdir(exist_ok=True)
data = json.loads((ROOT / "examples/secom/results.json").read_text(encoding="utf-8"))
html = (
    (ROOT / "app/static/index.html")
    .read_text(encoding="utf-8")
    .replace('href="/static/', 'href="./static/')
    .replace('src="/static/', 'src="./static/')
)
html = html.replace(
    '<script src="./static/workspace.js"',
    '<script src="./static/recording.js"></script><script src="./static/workspace.js"',
)
(dest / "index.html").write_text(html, encoding="utf-8")
for name in ("workspace.css", "workspace.js"):
    shutil.copyfile(ROOT / "app/static" / name, dest / "static" / name)
(dest / "static/recording.js").write_text(
    "window.__NL_RECORDED = " + json.dumps(data, ensure_ascii=True) + ";\n", encoding="utf-8"
)
(dest / "README.txt").write_text(
    "Open index.html to inspect explicitly recorded public evidence. This package does not execute code or call models.\n",
    encoding="utf-8",
)
manifest = {
    p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in dest.rglob("*")
    if p.is_file() and p.name != "manifest.json"
}
(dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
with zipfile.ZipFile(ROOT / "out" / "nulllab-public-demo.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(dest))
print(ROOT / "out" / "nulllab-public-demo.zip")
