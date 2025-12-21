from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WebAssets:
    web_root: Path
    html_out: Path
    svg_path: Path
    html_template_raw: str


def prepare_web_assets() -> WebAssets:
    """
    Stages a self-contained web root for QWebEngine:

    %TEMP%/score_beats_web/web/
        beatpage.html        <-- processed (placeholders replaced)
        js/                  <-- copied ES modules
            app.js, dom.js, cursor.js, geom.js, sidebar.js, state.js, utils.js
    """
    module_dir = Path(__file__).resolve().parent  # .../beat_selector

    html_template = module_dir / "beatpage.html"
    if not html_template.exists():
        raise FileNotFoundError(f"HTML template not found: {html_template}")

    js_source_dir = module_dir
    wanted = ["app.js", "dom.js", "cursor.js", "geom.js", "sidebar.js", "state.js", "utils.js"]
    for name in wanted:
        if not (js_source_dir / name).exists():
            raise FileNotFoundError(f"Missing JS module: {js_source_dir / name}")

    tmp_root = Path(tempfile.gettempdir()) / "score_beats_web" / "web"
    js_out = tmp_root / "js"
    tmp_root.mkdir(parents=True, exist_ok=True)
    js_out.mkdir(parents=True, exist_ok=True)

    for name in wanted:
        shutil.copyfile(js_source_dir / name, js_out / name)

    html_template_raw = html_template.read_text(encoding="utf-8")
    html_out = tmp_root / "beatpage.html"
    svg_path = Path(tempfile.gettempdir()) / "score_page_beats.svg"

    return WebAssets(
        web_root=tmp_root,
        html_out=html_out,
        svg_path=svg_path,
        html_template_raw=html_template_raw,
    )
