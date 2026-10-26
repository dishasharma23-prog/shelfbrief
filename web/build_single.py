"""Bundles the site into one self-contained HTML file (data, CSS and JS inlined) for sharing as a single page.
Usage: python web/build_single.py [output.html]"""
import json
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
html = (WEB / "index.html").read_text(encoding="utf-8")
css = (WEB / "style.css").read_text(encoding="utf-8")
app = (WEB / "app.js").read_text(encoding="utf-8")
scene = (WEB / "scene.js").read_text(encoding="utf-8")
data = json.loads((WEB / "data" / "site.json").read_text(encoding="utf-8"))

head_start, head_end = html.index("<title>"), html.index("</head>")
head = html[head_start:head_end].replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
body = html[html.index("<!--BODY-->") + len("<!--BODY-->"):html.index("<!--/BODY-->")]
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
out = (head + body
       + f'<script>window.SHELF_DATA = {payload};</script>\n'
       + f'<script type="module">\n{app}\n</script>\n'
       + f'<script type="module">\n{scene}\n</script>\n')
target = Path(sys.argv[1]) if len(sys.argv) > 1 else WEB.parent / "dist" / "shelfbrief.html"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(out, encoding="utf-8")
print(f"wrote {target} ({len(out) // 1024} KB)")
