import argparse
import base64
import datetime as dt
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from tikz_harness.templates import library as templates_mod


OPENAI_MODEL = "gpt-5.4-nano"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TEXT_MODELS = "openai/gpt-oss-120b,qwen/qwen3-32b,moonshotai/kimi-k2-instruct"
GROQ_MAVERICK_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"  # maverick not accessible on this key
EMBED_BASE_URL = "http://localhost:1234/v1"
EMBED_MODEL = "text-embedding-bge-large-en-v1.5"
EMBED_TIMEOUT = 1.0
MAX_TOKENS = 2200
QWEN_MAX_TOKENS = 1300
BUNDLED_TECTONIC_ROOT = Path.home() / ".codex" / "plugins" / "cache" / "openai-bundled" / "latex"


SYSTEM_PROMPT = r"""You generate clean TikZ figures for school worksheets, mainly grades 5-12.
Return exactly one \begin{tikzpicture}...\end{tikzpicture}. No markdown. No explanation.

Reliability rules:
- Use plain TikZ only: \draw, \fill, \node, \coordinate, \path, \foreach.
- No \def, \newcommand, \pgfmathsetmacro, circuitikz syntax, custom projections, or obscure libraries.
- Use explicit numeric coordinates. For 3D, draw a simple oblique 2D projection.
- Keep the figure in about x=-5..5 and y=-4..4.
- Use black, gray, dashed, dotted, and thickness before color.
- Use at most 45 non-empty TikZ lines.

Worksheet quality rules:
- One main figure, centered, with generous whitespace.
- Labels must sit outside lines/arrows/shapes. Use short labels and offset them.
- Put formulas below the figure, not over the drawing.
- Do not crowd repeated objects; label representative pieces.
- For force diagrams: object geometry first, then arrows from the object center; weight vertical, normal perpendicular, friction parallel.
- For ray optics: lens/mirror shapes must be physically correct; rays should be few and readable.
- For chemistry: benzene must be aromatic hexagon with inner circle or alternating double bonds, not cyclohexane.
- Prefer a simpler correct diagram over a decorative crowded one.
"""

BLUEPRINT_SYSTEM_PROMPT = r"""You are a spatial planner for school worksheet figures (grades 5-12).
Given a worksheet request, return ONLY a JSON object describing WHERE everything goes.
Do NOT return TikZ or any drawing code. No markdown, no prose, no code fences.

Reason about layout explicitly and avoid collisions. Keep the whole figure inside
roughly x in [-5,5] and y in [-4,4]. Labels must sit OUTSIDE the shapes/lines they name.

Return exactly this schema:
{
  "canvas": {"xmin": -5, "xmax": 5, "ymin": -4, "ymax": 4},
  "objects": [
    {"id": "unique_string", "type": "line|circle|rect|polygon|arrow|arc|point|curve",
     "coords": [[x,y], ...], "size": {"w": 0, "h": 0, "r": 0}, "style": "black|gray|dashed|dotted|thick"}
  ],
  "labels": [
    {"text": "short label", "anchor_id": "an object id",
     "direction": "above|below|left|right|above left|above right|below left|below right",
     "offset": 0.35}
  ],
  "relations": ["free-text notes like 'block base lies on ramp surface'"]
}

Rules:
- Every label.anchor_id must match some object.id.
- Give each object explicit numeric coordinates. For 3D use a simple oblique 2D projection.
- Keep it simple and correct: one main figure, generous whitespace, no crowding.
- Do not place two labels at the same anchor+direction; spread them out.
"""

CODE_SYSTEM_PROMPT = r"""You convert a JSON figure blueprint into clean TikZ for a school worksheet.
Return exactly one \begin{tikzpicture}...\end{tikzpicture}. No markdown. No explanation.

- Honor every coordinate, size, offset, and label direction in the blueprint. Do not invent
  new objects or move things around.
- Use plain TikZ only: \draw, \fill, \node, \coordinate, \path, \foreach.
- No \def, \newcommand, \pgfmathsetmacro, circuitikz syntax, or obscure libraries.
- Place each label outside its anchor using its direction/offset. Keep labels off lines/arrows.
- Use black, gray, dashed, dotted, and thickness before color. At most 45 non-empty lines.
"""

BRIEF_SYSTEM_PROMPT = r"""You expand short worksheet diagram requests into a precise drawing brief.
Return plain text only, no markdown, no TikZ, no JSON.

Write 6-10 short sentences covering:
- the main objects and their relative positions
- key labels and formulas
- force/ray/field/axis directions where relevant
- what to keep uncrowded or outside the figure
- any common mistakes to avoid

Keep it specific enough that another model can draw the diagram, but do not solve by
hardcoding a generic template. Preserve the user's requested topic and labels."""

CRITIQUE_RUBRIC = r"""You are reviewing a rendered school-worksheet figure image.
Judge ONLY what you can see. Return ONLY a JSON object, no markdown, no prose:
{
  "score": 0-10,
  "overlaps": true/false,
  "geometry_correct": true/false,
  "crowded": true/false,
  "issues": ["short, specific problems you can see"],
  "fix_hint": "one concrete instruction to improve the layout"
}
Score high (8-10) only if labels are readable and outside shapes, geometry is physically
correct, and the figure is uncrowded. Penalize overlapping labels/arrows, floating or
mis-seated objects, wrong shapes, and clutter. The worksheet request was:
"""

CATEGORY_HINTS = [
    (
        (r"benzene", r"aromatic"),
        "Benzene: draw one regular hexagon with one inner circle. Do not put C labels on every vertex; only label C6H6 below.",
    ),
    (
        (r"convex lens", r"concave lens", r"ray diagram"),
        "Ray optics: draw a large vertical lens/mirror, horizontal principal axis, focal labels below the axis, and exactly two clean rays. Keep labels off the rays and axis.",
    ),
    (
        (r"inclined plane", r"block on .*plane", r"slope"),
        "Inclined plane recipe: use ramp points (-4,-1.5),(3,-1.5),(3,1.0). Put the block in a rotated scope near (0.8,-0.15), rotate=20, rectangle (-0.45,0) to (0.45,0.55), so its base lies on the slope. Draw forces from the block center: mg vertical down, N perpendicular up-left, f parallel along the slope.",
    ),
    (
        (r"circuit", r"battery", r"voltmeter", r"ammeter"),
        "Circuit recipe: draw a simple rectangular loop. Battery on left, switch on top-left, resistor as one box on the right side, ammeter circle on bottom wire, voltmeter circle on a separate parallel branch across only the resistor. Use no color.",
    ),
    (
        (r"pulley", r"hanging mass"),
        "Pulley recipe: table from x=-4 to 1 at y=0, block on table at left, pulley circle at (1.5,0.8), hanging mass to the right below the pulley, one continuous string, and force arrows outside the blocks. Do not put force text on top of masses.",
    ),
    (
        (r"distillation", r"condenser", r"boiling flask"),
        "Distillation recipe: draw one round boiling flask at left, a short neck upward, a straight condenser tube slanting gently right, one receiver flask at right, and two short water in/out arrows on the condenser. Use only a few large shapes and label them outside.",
    ),
    (
        (r"electric field", r"electrostatics", r"\+q", r"-q"),
        "Electrostatics: use black/gray only. Draw a few smooth field lines from +q to -q; keep labels outside field lines.",
    ),
]


PROMPTS = {
    "geometry": "Create a labeled triangle ABC with side lengths 5 cm, 6 cm, 7 cm and one marked angle at A.",
    "coordinate": "Create a coordinate plane with grid, axes, points A(-2,1) and B(3,4), and the segment AB.",
    "fraction": "Create a number line from 0 to 1 split into eighths, with 3/8 emphasized.",
}

ADVANCED_PROMPTS = {
    "vectors": r"Draw vector addition in 2D: vectors $\vec a$ and $\vec b$, head-to-tail construction, resultant $\vec r=\vec a+\vec b$, components, and angle $\theta$.",
    "3d-geometry": r"Draw a rectangular cuboid with hidden edges, vertices A-H, dimensions l,w,h, and space diagonal AG.",
    "free-body": r"Draw a block on an inclined plane angle $\theta$ with forces $mg$, $N$, $f$, and components $mg\sin\theta$, $mg\cos\theta$.",
    "ray-optics": r"Draw a convex lens ray diagram with object, image, focal points, principal axis, and two principal rays.",
    "chemistry": r"Draw benzene as an aromatic ring, clearly not cyclohexane, with label C6H6.",
    "electrostatics": r"Draw two charges +q and -q with electric field lines, force arrows, distance r, and labels.",
}


def load_env(path=".env"):
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def post_json(url, headers, payload, timeout, max_retries=4):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "trying-tikz/0.2", **headers},
        method="POST",
    )
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # Back off and retry on rate limits (429) so big multi-model runs don't abort.
            if exc.code == 429 and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(30, 2 ** attempt)
                time.sleep(wait)
                continue
            raise RuntimeError(f"{exc.code} {exc.reason}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, http.client.RemoteDisconnected, socket.timeout) as exc:
            if attempt < max_retries:
                time.sleep(min(8, 2 ** attempt))
                continue
            raise


def openai_text(data):
    if data.get("output_text"):
        return data["output_text"]
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if "text" in content:
                parts.append(content["text"])
    return "\n".join(parts).strip()


def call_openai(model, prompt, timeout, system=SYSTEM_PROMPT):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    started = time.perf_counter()
    data = post_json(
        "https://api.openai.com/v1/responses",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {
            "model": model,
            "instructions": system,
            "input": prompt,
            "max_output_tokens": MAX_TOKENS,
            "temperature": 0,
        },
        timeout,
    )
    return openai_text(data), time.perf_counter() - started, data.get("usage")


def call_groq(model, prompt, timeout, system=SYSTEM_PROMPT):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    if model.startswith("qwen"):
        # ponytail: force answers over hidden reasoning; this model was spending the whole
        # token budget thinking and returning empty tikzpictures.
        payload["reasoning_format"] = "hidden"
        payload["reasoning_effort"] = "none"
        payload["max_completion_tokens"] = QWEN_MAX_TOKENS
    started = time.perf_counter()
    data = post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload,
        timeout,
    )
    return data["choices"][0]["message"]["content"], time.perf_counter() - started, data.get("usage")


def call_groq_vision(model, image_b64, prompt, timeout):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }
        ],
        "max_completion_tokens": 700,
        "temperature": 0,
    }
    started = time.perf_counter()
    data = post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload,
        timeout,
    )
    return data["choices"][0]["message"]["content"], time.perf_counter() - started, data.get("usage")


def clean_tikz(text):
    text = text.strip()
    text = re.sub(r"^```(?:tex|latex|tikz)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", text, re.S)
    return fix_unsafe_macros(match.group(0).strip() if match else text)


def fix_unsafe_macros(tikz):
    tikz = re.sub(r"\\mathrm\{([^{}]*?)\\text\{([^{}]*?)\}([^{}]*?)\}", r"\\mathrm{\1\2\3}", tikz)
    tikz = re.sub(r"\\\((.*?)\\\)", r"$\1$", tikz, flags=re.S)
    tikz = re.sub(r"\bat\s+(\\[A-Za-z]+)\b", r"at (\1)", tikz)
    tikz = re.sub(r"\\node\s+at\s+(\([^)]+\))\s+\+\+\(([^)]+)\)", r"\\node at ($\1+(\2)$)", tikz)
    return tikz


def parse_json_loose(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0) if match else text)


def _label_box(label, objects_by_id):
    anchor = objects_by_id.get(label.get("anchor_id"))
    if not anchor or not anchor.get("coords"):
        return None
    ax = sum(c[0] for c in anchor["coords"]) / len(anchor["coords"])
    ay = sum(c[1] for c in anchor["coords"]) / len(anchor["coords"])
    offset = float(label.get("offset", 0.35) or 0.35)
    dx = {"left": -1, "right": 1}
    dy = {"above": 1, "below": -1}
    direction = str(label.get("direction", ""))
    x = ax + offset * sum(v for k, v in dx.items() if k in direction)
    y = ay + offset * sum(v for k, v in dy.items() if k in direction)
    w = max(0.4, 0.14 * len(str(label.get("text", ""))))
    return (x - w / 2, y - 0.2, x + w / 2, y + 0.2)


def _boxes_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def lint_blueprint(bp):
    """Deterministic quality gate on the JSON, no rendering."""
    warnings = []
    canvas = bp.get("canvas", {})
    objects = bp.get("objects", []) or []
    objects_by_id = {o.get("id"): o for o in objects if o.get("id")}
    xmin, xmax = canvas.get("xmin", -5), canvas.get("xmax", 5)
    ymin, ymax = canvas.get("ymin", -4), canvas.get("ymax", 4)
    for obj in objects:
        for pt in obj.get("coords", []) or []:
            if len(pt) >= 2 and not (xmin - 0.01 <= pt[0] <= xmax + 0.01 and ymin - 0.01 <= pt[1] <= ymax + 0.01):
                warnings.append("object_out_of_bounds")
                break
    coord_seen = {}
    for obj in objects:
        key = json.dumps(obj.get("coords"))
        if obj.get("coords") and key in coord_seen:
            warnings.append("objects_share_coords")
        coord_seen[key] = obj.get("id")
    labels = bp.get("labels", []) or []
    boxes = []
    for label in labels:
        if label.get("anchor_id") not in objects_by_id:
            warnings.append("label_anchor_missing")
            continue
        box = _label_box(label, objects_by_id)
        if box:
            if any(_boxes_overlap(box, other) for other in boxes):
                warnings.append("label_overlap")
            boxes.append(box)
    if len(objects) > 22:
        warnings.append("too_many_objects")
    return sorted(set(warnings))


def wrap_tex(tikz):
    if r"\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n" + tikz + "\n\\end{tikzpicture}"
    return f"""\\documentclass[tikz,border=5pt]{{standalone}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{tikz}}
\\usetikzlibrary{{arrows.meta,calc,decorations.pathreplacing,intersections,patterns,positioning,quotes}}
\\begin{{document}}
{tikz}
\\end{{document}}
"""


def find_compiler():
    for name in ("tectonic", "pdflatex", "lualatex"):
        found = shutil.which(name)
        if found:
            return found
    bundled = sorted(BUNDLED_TECTONIC_ROOT.glob("*/bin/tectonic.exe")) if BUNDLED_TECTONIC_ROOT.exists() else []
    return str(bundled[-1]) if bundled else None


def render(tex_path):
    compiler = find_compiler()
    if not compiler:
        return {"rendered": False, "compiler": None, "pdf": None, "error": "No TeX compiler found"}
    cmd = [compiler, tex_path.name] if Path(compiler).stem == "tectonic" else [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_path.name,
    ]
    try:
        proc = subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except subprocess.TimeoutExpired:
        return {"rendered": False, "compiler": str(compiler), "pdf": None, "error": f"Compiler timed out after 60 seconds: {tex_path.name}"}
    pdf_path = tex_path.with_suffix(".pdf")
    return {
        "rendered": proc.returncode == 0 and pdf_path.exists(),
        "compiler": str(compiler),
        "pdf": str(pdf_path) if pdf_path.exists() else None,
        "error": None if proc.returncode == 0 else (proc.stderr or proc.stdout)[-2000:],
    }


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "prompt"


def source_stats(tikz):
    meaningful = [line for line in tikz.splitlines() if line.strip() and not line.lstrip().startswith("%")]
    return {
        "nonempty_lines": len(meaningful),
        "nodes": len(re.findall(r"\\node\b", tikz)),
        "draws": len(re.findall(r"\\draw\b", tikz)),
        "coordinates": len(re.findall(r"\\coordinate\b", tikz)),
    }


def source_error(tikz, stats):
    body = re.sub(r"\\begin\{tikzpicture\}|\s*\\end\{tikzpicture\}", "", tikz, flags=re.S).strip()
    if not body:
        return "Model returned an empty tikzpicture"
    if stats["nonempty_lines"] > 70:
        return "TikZ is too long; likely off prompt"
    if "intersection of" in tikz:
        return "Unsupported intersection syntax; use explicit coordinates or named paths with name intersections"
    for name, pattern in {
        "\\def": r"\\def\b",
        "\\newcommand": r"\\newcommand\b",
        "\\pgfmathsetmacro": r"\\pgfmathsetmacro\b",
    }.items():
        if re.search(pattern, tikz):
            return f"Unsupported {name}; use explicit coordinates and repeated literals"
    if not (stats["draws"] or stats["nodes"] or stats["coordinates"] or re.search(r"\\path\b", tikz)):
        return "TikZ has no drawing commands"
    return None


def source_warnings(tikz, stats, prompt=""):
    checks = {
        "possible_circuitikz": r"\bto\[(?!(?:out|in)\b)[^]]+\]",
        "possible_complex_calc": r"\$\([^)]*[*/][^)]*\)\$",
    }
    warnings = [name for name, pattern in checks.items() if re.search(pattern, tikz)]
    color_pattern = r"\b(red|blue|green|orange|purple|violet)\b"
    if re.search(color_pattern, tikz) and not re.search(color_pattern + r"|color|colou?r", prompt, re.I):
        warnings.append("uses_raw_color")
    if stats["nonempty_lines"] > 55:
        warnings.append("long_source")
    if stats["nodes"] > 18:
        warnings.append("many_labels")
    return warnings


def write_candidate(run_dir, provider, model, prompt_name, prompt, text, latency, usage, attempt,
                    blueprint=None, blueprint_warnings=None):
    tikz = clean_tikz(text)
    stem = f"{provider}-{slug(model)}-{prompt_name}-a{attempt}"
    tikz_path = run_dir / f"{stem}.tikz"
    tex_path = run_dir / f"{stem}.tex"
    tikz_path.write_text(tikz + "\n", encoding="utf-8")
    tex_path.write_text(wrap_tex(tikz), encoding="utf-8")
    blueprint_path = None
    if blueprint is not None:
        blueprint_path = run_dir / f"{stem}.blueprint.json"
        blueprint_path.write_text(json.dumps(blueprint, indent=2), encoding="utf-8")
    stats = source_stats(tikz)
    warnings = source_warnings(tikz, stats, prompt)
    error = source_error(tikz, stats)
    if not error and "uses_raw_color" in warnings:
        error = "Unexpected raw color; use black, gray, dashed, dotted, or thickness unless the prompt asks for color"
    render_result = {"rendered": False, "compiler": None, "pdf": None, "error": error} if error else render(tex_path)
    result = {
        "provider": provider,
        "model": model,
        "prompt_name": prompt_name,
        "prompt": prompt,
        "attempt": attempt,
        "latency_seconds": round(latency, 3),
        "usage": usage,
        "tikz": str(tikz_path),
        "tex": str(tex_path),
        "blueprint": str(blueprint_path) if blueprint_path else None,
        "blueprint_warnings": blueprint_warnings or [],
        "source_stats": stats,
        "warnings": warnings,
        **render_result,
    }
    result["score"] = score(result)
    return result


def repair_prompt(original_prompt, tikz, error):
    return f"""Repair this TikZ for the same worksheet prompt.

Worksheet prompt:
{original_prompt}

Compiler/error feedback:
{error}

Bad TikZ:
{tikz}

Return only corrected TikZ."""


def polish_prompt(original_prompt, tikz):
    return f"""Improve this compiled TikZ for a grade 5-12 worksheet.

Original worksheet prompt:
{enrich_prompt(original_prompt)}

Visual checklist:
- no overlapping labels, arrows, axes, or formulas
- no color unless the prompt explicitly asks for it
- object geometry must be physically correct
- forces/rays/field lines must be readable and not crowded
- simpler is better; remove decorative or repeated clutter

Current TikZ:
{tikz}

Return only improved TikZ."""


def code_input(blueprint):
    return "Blueprint:\n" + json.dumps(blueprint, indent=2)


def blueprint_repair_prompt(enriched_prompt, blueprint, critique):
    return f"""Revise this figure blueprint to fix the visual problems found in the rendered image.

Worksheet request:
{enriched_prompt}

Reviewer feedback (from looking at the rendered picture):
{json.dumps(critique, indent=2)}

Current blueprint:
{json.dumps(blueprint, indent=2)}

Return only the corrected JSON blueprint using the same schema. Move labels off shapes, fix
overlaps and geometry, and keep everything inside the canvas."""


def render_png(pdf_path):
    """Rasterize page 1 of a PDF to base64 PNG. Returns None if PyMuPDF is unavailable."""
    try:
        import fitz
    except ImportError:
        return None
    doc = fitz.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return base64.b64encode(pix.tobytes("png")).decode("ascii")
    finally:
        doc.close()


def vision_critique(vision_model, pdf_path, worksheet_prompt, timeout):
    """Stage 3 helper: show the rendered image to a vision model, get a structured critique."""
    image_b64 = render_png(pdf_path)
    if not image_b64:
        return None
    prompt = CRITIQUE_RUBRIC + worksheet_prompt
    text, latency, usage = call_groq_vision(vision_model, image_b64, prompt, timeout)
    try:
        critique = parse_json_loose(text)
    except (json.JSONDecodeError, ValueError):
        return {"score": 5, "issues": ["vision model returned unparseable critique"],
                "fix_hint": text[:300], "latency_seconds": round(latency, 3), "usage": usage}
    critique["latency_seconds"] = round(latency, 3)
    critique["usage"] = usage
    return critique


def score(candidate):
    """Numeric quality score: compile is a hard gate, then fewer warnings + vision score win."""
    if not candidate.get("rendered"):
        return -100
    vision = candidate.get("vision") or {}
    vision_score = vision.get("score")
    base = float(vision_score) if isinstance(vision_score, (int, float)) else 6.0
    base -= 0.5 * len(candidate.get("warnings", []))
    base -= 0.5 * len(candidate.get("blueprint_warnings", []))
    return round(base, 3)


def enrich_prompt(prompt):
    key = prompt.lower()
    hints = [hint for patterns, hint in CATEGORY_HINTS if any(re.search(pattern, key) for pattern in patterns)]
    if not hints:
        return prompt
    return prompt + "\n\nExtra diagram-specific guidance:\n- " + "\n- ".join(hints)


# ---- Pipeline B: semantic template retrieval ------------------------------------------

_EMBED_CACHE = {}


def embed_texts(texts, timeout=None):
    """Embed texts via a local OpenAI-compatible endpoint (e.g. LM Studio serving BGE)."""
    base = os.environ.get("EMBED_BASE_URL", EMBED_BASE_URL).rstrip("/")
    timeout = float(os.environ.get("EMBED_TIMEOUT", timeout or EMBED_TIMEOUT))
    data = post_json(
        f"{base}/embeddings",
        {"Content-Type": "application/json"},
        {"model": os.environ.get("EMBED_MODEL", EMBED_MODEL), "input": texts},
        timeout,
        max_retries=0,
    )
    return [row["embedding"] for row in data["data"]]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0


def retrieve_template(prompt, min_score=0.15):
    """Return (name, template, method, score) of the best-matching template, or None.

    Prefers embedding cosine-similarity over the local BGE endpoint; falls back to token
    Jaccard overlap when the endpoint is unreachable so pipeline B still runs offline.
    """
    items = list(templates_mod.TEMPLATES.items())
    descriptions = [t["description"] for _, t in items]
    try:
        if _EMBED_CACHE.get("disabled"):
            raise RuntimeError("embedding endpoint disabled after earlier failure")
        if "descriptions" not in _EMBED_CACHE:
            _EMBED_CACHE["descriptions"] = embed_texts(descriptions)
        qvec = embed_texts([prompt])[0]
        scores = [_cosine(qvec, dvec) for dvec in _EMBED_CACHE["descriptions"]]
        method = "embedding"
    except Exception:
        _EMBED_CACHE["disabled"] = True
        scores = [_jaccard(prompt, desc) for desc in descriptions]
        method = "jaccard"
    best = max(range(len(items)), key=lambda i: scores[i])
    if scores[best] < min_score:
        return None
    name, template = items[best]
    return name, template, method, round(scores[best], 3)


def templates_prompt(prompt, detailed_prompt, template):
    example = ""
    if template:
        example = f"""
Similar TikZ example, for few-shot guidance only:
{template['description']}
{template['tikz']}

Use this example to understand the diagram family's conventions, spacing, and common
direction rules. Do not copy it exactly; produce a fresh diagram for the request."""
    return f"""Original request:
{prompt}

Expanded drawing brief:
{detailed_prompt}
{example}

Return only one tikzpicture."""


def call_provider(provider, model, prompt, timeout, system=SYSTEM_PROMPT):
    if provider == "openai":
        return call_openai(model, prompt, timeout, system)
    return call_groq(model, prompt, timeout, system)


def _call_with_fallback(provider, model, prompt, timeout, system):
    """Call the provider, downgrading Groq gpt-oss to a fallback model on tool_use_failed."""
    try:
        return model, call_provider(provider, model, prompt, timeout, system)
    except RuntimeError as exc:
        if provider == "groq" and "tool_use_failed" in str(exc) and model == GROQ_MODEL:
            return GROQ_FALLBACK_MODEL, call_provider(provider, GROQ_FALLBACK_MODEL, prompt, timeout, system)
        raise


def expand_diagram_prompt(provider, model, prompt, timeout):
    model, (text, latency, usage) = _call_with_fallback(provider, model, prompt, timeout, BRIEF_SYSTEM_PROMPT)
    return model, text.strip(), latency, usage


def _compile_with_repairs(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                          initial_text, initial_meta, blueprint, blueprint_warnings, tag):
    """Write a candidate and repair compile errors up to `retries` times. Returns (best, results)."""
    results = []
    latency, usage = initial_meta
    result = write_candidate(run_dir, provider, model, prompt_name, prompt, initial_text, latency, usage,
                             f"{tag}0", blueprint, blueprint_warnings)
    results.append(result)
    for attempt in range(1, retries + 1):
        if result["rendered"]:
            break
        repair = repair_prompt(prompt, Path(result["tikz"]).read_text(encoding="utf-8"), result.get("error"))
        model, (text, latency, usage) = _call_with_fallback(provider, model, repair, timeout, SYSTEM_PROMPT)
        result = write_candidate(run_dir, provider, model, prompt_name, prompt, text, latency, usage,
                                 f"{tag}{attempt}", blueprint, blueprint_warnings)
        results.append(result)
    return result, results


def generate_with_repairs(run_dir, provider, model, prompt_name, prompt, timeout, retries, polish,
                          pipeline="vision", vision_model=GROQ_MAVERICK_VISION, critique=2):
    """Dispatch to one of the three comparison pipelines. Returns all candidates.

    enrich_prompt/CATEGORY_HINTS are deliberately bypassed in all three so the only variable
    is the mechanism under test: nothing (plain) vs template exemplar (templates) vs
    blueprint+vision-critique (vision).
    """
    if pipeline == "plain":
        from tikz_harness.pipelines import plain
        return plain.run(run_dir, provider, model, prompt_name, prompt, timeout, retries)
    if pipeline == "templates":
        from tikz_harness.pipelines import template_guided
        return template_guided.run(run_dir, provider, model, prompt_name, prompt, timeout, retries)
    from tikz_harness.pipelines import vision
    return vision.run(run_dir, provider, model, prompt_name, prompt, timeout, retries, vision_model, critique)


def fatal_provider_error(error):
    return any(text in error for text in ("API_KEY is missing", "billing_not_active", "401 Unauthorized", "403 Forbidden"))


def best_results(results, by_model=False):
    final = {}
    for item in results:
        if "prompt_name" not in item:
            continue
        key = (item.get("provider"), item.get("prompt_name"))
        if by_model:
            key = key + (item.get("model"),)
        current = final.get(key)
        if current is None or item.get("score", -100) > current.get("score", -100):
            final[key] = item
    return final


def summarize(results):
    final = best_results(results)
    rendered = sum(1 for item in final.values() if item.get("rendered"))
    warnings = sum(len(item.get("warnings", [])) for item in final.values())
    scored = [item["score"] for item in final.values() if item.get("rendered") and isinstance(item.get("score"), (int, float))]
    return {
        "rendered": rendered,
        "total": len(final),
        "pass_rate": round(rendered / len(final), 3) if final else 0,
        "total_tokens": sum((item.get("usage") or {}).get("total_tokens", 0) for item in results),
        "warning_count": warnings,
        "mean_score": round(sum(scored) / len(scored), 3) if scored else None,
        "failures": [
            {
                "prompt_name": item.get("prompt_name"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "error": item.get("error"),
            }
            for item in final.values()
            if not item.get("rendered")
        ],
    }


def collect_best_pdfs(src="runs", dest="best-pdfs", by_model=False):
    src = Path(src)
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    chosen = {}
    for summary_path in sorted(src.glob("**/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in best_results(summary.get("results", []), by_model=by_model).values():
            name = item.get("prompt_name")
            model = item.get("model", "unknown").replace("/", "_")
            key = f"{name}-{model}" if by_model else name
            if not name or key in chosen or not item.get("rendered") or not item.get("pdf"):
                continue
            pdf = Path(item["pdf"])
            if not pdf.exists():
                continue
            # Prefix with prompt so a prompt's model variants sort adjacently in the sheet.
            out = dest / f"{name}__{model}.pdf"
            shutil.copy2(pdf, out)
            chosen[key] = {"prompt_name": name, "model": item.get("model"), "source": str(pdf),
                           "copied": str(out), "score": item.get("score")}
    print(json.dumps({"dest": str(dest), "count": len(chosen), "items": chosen}, indent=2))
    return chosen


def make_contact_sheets(src="best-pdfs", dest="visual-review", cols=4, thumb_width=340, thumb_height=240):
    try:
        import fitz
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("Contact sheets need PyMuPDF and Pillow: pip install pymupdf pillow") from exc
    src = Path(src)
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    pdfs = sorted(src.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {src}")
    label_height = 38
    gutter = 18
    rows = 3
    per_sheet = cols * rows
    sheets = []
    for offset in range(0, len(pdfs), per_sheet):
        batch = pdfs[offset:offset + per_sheet]
        sheet = Image.new("RGB", (cols * thumb_width + (cols + 1) * gutter, rows * (thumb_height + label_height) + (rows + 1) * gutter), "white")
        draw = ImageDraw.Draw(sheet)
        for index, pdf_path in enumerate(batch):
            row, col = divmod(index, cols)
            x = gutter + col * (thumb_width + gutter)
            y = gutter + row * (thumb_height + label_height + gutter)
            doc = fitz.open(pdf_path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            image.thumbnail((thumb_width, thumb_height), Image.LANCZOS)
            sheet.paste(image, (x + (thumb_width - image.width) // 2, y))
            draw.rectangle([x, y, x + thumb_width, y + thumb_height], outline=(210, 210, 210))
            draw.text((x, y + thumb_height + 6), pdf_path.stem[:48], fill=(0, 0, 0))
            doc.close()
        out = dest / f"sheet-{len(sheets) + 1:02d}.jpg"
        sheet.save(out, quality=92)
        sheets.append(str(out))
    print(json.dumps({"dest": str(dest), "pdfs": len(pdfs), "sheets": sheets}, indent=2))


def load_prompts(args):
    if args.prompt_suite_file:
        return json.loads(Path(args.prompt_suite_file).read_text(encoding="utf-8"))
    if args.prompt_file:
        return {"custom": Path(args.prompt_file).read_text(encoding="utf-8").strip()}
    if args.prompt:
        return {"custom": args.prompt}
    if args.suite == "advanced":
        return ADVANCED_PROMPTS
    if args.suite == "all":
        return {**PROMPTS, **ADVANCED_PROMPTS}
    return PROMPTS


def main():
    parser = argparse.ArgumentParser(description="Compare OpenAI and Groq on worksheet TikZ generation.")
    parser.add_argument("--provider", choices=("openai", "groq", "both"), default="both")
    parser.add_argument("--openai-model", default=OPENAI_MODEL)
    parser.add_argument("--groq-model", default=GROQ_MODEL)
    parser.add_argument("--suite", choices=("basic", "advanced", "all"), default="basic")
    parser.add_argument("--prompt-style", choices=("normal", "detailed"), default="detailed", help="Compatibility flag; prompt is already detailed.")
    parser.add_argument("--only", help="Comma-separated prompt names to run.")
    parser.add_argument("--prompt", help="Run one custom worksheet figure prompt.")
    parser.add_argument("--prompt-file", help="Read one custom prompt from a text file.")
    parser.add_argument("--prompt-suite-file", help="Read a JSON object of prompt_name to prompt.")
    parser.add_argument("--retries", type=int, default=1, help="Compile-repair retries per prompt.")
    parser.add_argument("--polish", type=int, default=1, help="Compatibility flag (blind polish).")
    parser.add_argument("--pipeline", choices=("plain", "templates", "vision"), default="vision", help="Generation strategy.")
    parser.add_argument("--groq-models", default=GROQ_MODEL, help="Comma-separated Groq text models to run.")
    parser.add_argument("--vision-model", default=GROQ_MAVERICK_VISION, help="Groq multimodal model for the critique loop.")
    parser.add_argument("--critique", type=int, default=2, help="Max vision-critique/repair iterations after a successful compile.")
    parser.add_argument("--compare", action="store_true", help="Run all 3 pipelines x all --groq-models and build a contact sheet per pipeline.")
    parser.add_argument("--collect-best", action="store_true")
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--by-model", action="store_true", help="Keep the best PDF per (prompt, model) when collecting.")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--best-dir", default="best-pdfs")
    parser.add_argument("--review-dir", default="visual-review")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if args.collect_best:
        collect_best_pdfs(args.runs_dir, args.best_dir, by_model=args.by_model)
        return
    if args.contact_sheet:
        make_contact_sheets(args.best_dir, args.review_dir)
        return

    load_env()
    prompts = load_prompts(args)
    if args.only:
        wanted = {slug(name) for name in args.only.split(",")}
        prompts = {name: prompt for name, prompt in prompts.items() if slug(name) in wanted}
        if not prompts:
            raise SystemExit(f"No prompts matched --only {args.only!r}")

    if args.compare:
        run_comparison(prompts, args)
        return

    run_dir = Path(args.runs_dir) / dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir.mkdir(parents=True, exist_ok=True)
    model_pairs = _model_pairs(args)
    results = run_suite(prompts, args.pipeline, model_pairs, args, run_dir)

    summary = {"run_dir": str(run_dir), "pipeline": args.pipeline, "score": summarize(results), "results": results}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["score"], indent=2))


def _model_pairs(args):
    """Build the (provider, model) list to run. Groq may fan out over --groq-models."""
    pairs = []
    if args.provider in ("openai", "both"):
        pairs.append(("openai", args.openai_model))
    if args.provider in ("groq", "both"):
        for model in [m.strip() for m in args.groq_models.split(",") if m.strip()]:
            pairs.append(("groq", model))
    return pairs


def run_suite(prompts, pipeline, model_pairs, args, run_dir):
    """Run one pipeline over every prompt x (provider, model). Returns all candidate dicts."""
    results = []
    blocked = {}
    for prompt_name, prompt in prompts.items():
        prompt_name = slug(prompt_name)
        for provider, model in model_pairs:
            tag = (provider, model)
            if tag in blocked:
                results.append({"provider": provider, "model": model, "prompt_name": prompt_name, "prompt": prompt, "error": blocked[tag]})
                continue
            try:
                results.extend(generate_with_repairs(
                    run_dir, provider, model, prompt_name, prompt, args.timeout,
                    args.retries, args.polish, pipeline, args.vision_model, args.critique))
            except Exception as exc:
                error = str(exc)
                results.append({"provider": provider, "model": model, "prompt_name": prompt_name, "prompt": prompt, "error": error})
                if fatal_provider_error(error):
                    blocked[tag] = error
    return results


def run_comparison(prompts, args):
    """Bake-off driver: run plain/templates/vision, one contact sheet + summary per pipeline."""
    root = Path(args.runs_dir)
    model_pairs = _model_pairs(args)
    overview = {"root": str(root), "models": [m for _, m in model_pairs], "pipelines": {}}
    for pipeline in ("plain", "templates", "vision"):
        run_dir = root / pipeline / dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== pipeline: {pipeline} ({len(prompts)} prompts x {len(model_pairs)} models) ===")
        results = run_suite(prompts, pipeline, model_pairs, args, run_dir)
        score = summarize(results)
        (run_dir / "summary.json").write_text(
            json.dumps({"run_dir": str(run_dir), "pipeline": pipeline, "score": score, "results": results}, indent=2),
            encoding="utf-8")
        best_dir = root / f"{pipeline}-best"
        review_dir = root / f"{pipeline}-review"
        collect_best_pdfs(run_dir, best_dir, by_model=True)
        try:
            make_contact_sheets(best_dir, review_dir)
        except SystemExit as exc:
            print(f"contact sheet skipped for {pipeline}: {exc}")
        # per-(pipeline, model) pass rates
        per_model = {}
        for (prov, name, model), item in best_results(results, by_model=True).items():
            per_model.setdefault(model, {"rendered": 0, "total": 0})
            per_model[model]["total"] += 1
            per_model[model]["rendered"] += 1 if item.get("rendered") else 0
        overview["pipelines"][pipeline] = {"score": score, "per_model": per_model, "review_dir": str(review_dir)}
    (root / "comparison_summary.json").write_text(json.dumps(overview, indent=2), encoding="utf-8")
    print("\n" + json.dumps(overview["pipelines"], indent=2))


if __name__ == "__main__":
    main()
