import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


OPENAI_MODEL = "gpt-5.4-nano"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"
MAX_TOKENS = 2000
BUNDLED_TECTONIC_ROOT = Path.home() / ".codex" / "plugins" / "cache" / "openai-bundled" / "latex"

SYSTEM_PROMPT = """You generate worksheet-ready TikZ figures.
Return exactly one \\begin{tikzpicture}...\\end{tikzpicture}, with no markdown and no explanation.
Use only simple TikZ: \\draw, \\fill, \\node, \\coordinate, \\path, \\foreach.
Avoid \\def, \\newcommand, \\pgfmathsetmacro, custom projection macros, uncommon styles, circuitikz syntax like to[short], and complex calc expressions.
Use explicit numeric 2D coordinates. For 3D-looking figures, draw an oblique 2D projection manually.
Keep the diagram inside roughly x=-5..5 and y=-4..4, using scale between 0.8 and 1.3.
Use black, gray, dashed, dotted, and line thickness for meaning; avoid color unless necessary.
Plan whitespace: put the main figure centered, labels outside shapes, and leave at least 0.25 units between labels and lines.
Prevent overlaps: do not place labels on top of arrows, vertices, force vectors, axes, or other labels.
Prefer short labels and offset them with above/below/left/right/above right.
Use arrow tips with -> or <-> only; keep arrows long enough to read.
Every requested object must be visibly labeled.
Use at most 35 non-empty TikZ lines.
Code must compile in a standalone LaTeX document."""

PROMPTS = {
    "geometry": "Create a labeled triangle ABC with side lengths 5 cm, 6 cm, 7 cm and one marked angle at A.",
    "coordinate": "Create a coordinate plane with grid, axes, points A(-2,1) and B(3,4), and the segment AB.",
    "fraction": "Create a number line from 0 to 1 split into eighths, with 3/8 shaded or emphasized.",
}

ADVANCED_PROMPTS = {
    "vectors": r"Create a worksheet TikZ diagram for vector addition in 2D: vectors $\vec{a}$ and $\vec{b}$ from the origin, their head-to-tail construction, resultant $\vec{r}=\vec{a}+\vec{b}$, component labels, angle $\theta$, and a light grid.",
    "3d-geometry": r"Create a worksheet TikZ diagram for 3D geometry: a rectangular cuboid with visible and hidden edges, labeled vertices $A,B,C,D,E,F,G,H$, space diagonal $AG$, dimensions $l,w,h$, and a marked right angle.",
    "chemistry": r"Create a worksheet TikZ diagram for chemistry: a methane molecule $CH_4$ shown with central carbon, four hydrogens in tetrahedral style using wedge/dash bonds, bond angle label $109.5^\circ$, and clean labels.",
    "free-body": r"Create a worksheet TikZ free body diagram for a block on an inclined plane angle $\theta$: weight $mg$, normal force $N$, friction $f$, applied force $F$, axes parallel/perpendicular to plane, and component labels $mg\sin\theta$ and $mg\cos\theta$.",
    "rotational-motion": r"Create a worksheet TikZ diagram for rotational motion: a disk rotating about center $O$, angular velocity $\omega$, tangential velocity $v$, radius $r$, centripetal acceleration $a_c$, torque arrow $\tau$, and a point mass on the rim.",
    "gravitation": r"Create a worksheet TikZ diagram for gravitation: two masses $m_1$ and $m_2$ separated by distance $r$, equal and opposite gravitational forces $F=Gm_1m_2/r^2$, center-to-center distance line, and labels.",
    "electrostatics": r"Create a worksheet TikZ diagram for electrostatics: two point charges $+q$ and $-q$, electric field lines from positive to negative, force arrows, separation distance $r$, and a labeled test charge $q_0$ at a point.",
}

HARDCORE_PROMPTS = {
    "circle-tangents": r"Create a clean geometry diagram using these explicit coordinates: $O=(0,0)$, circle radius $2$, $S=(2,0)$, $P=(3.2,0)$, $T=(1.25,1.56)$, $Q=(1.25,-1.56)$. Draw the circle, line $O$-$S$-$P$, tangents $PT$ and $PQ$, radii $OT$ and $OQ$, right angle marks at $T$ and $Q$, labels $O,S,P,T,Q$, and a small label $r=10\text{ cm}$. Keep labels outside the lines with no overlap.",
    "similar-triangles": r"Create a clean similar-triangles diagram using explicit coordinates: $A=(0,0)$, $B=(5,0)$, $C=(0,3.75)$, $D=(2,0)$, $E=(0,1.5)$. Draw large right triangle $ABC$ and inner segment $DE$ parallel to $BC$. Label vertices outside. Label $AD=4$, $DB=6$, $AE=5$, and $EC=7.5$. Mark matching angles with two tiny straight line marks only, no arcs.",
    "vectors-3d": r"Create a 3D-looking vector diagram using only these 2D coordinates: $O=(0,0)$, $x$ axis to $(4,0)$, $y$ axis to $(-1.8,1.6)$, $z$ axis to $(1.2,3.2)$, vector $\vec v$ to $(3.0,2.6)$. Draw dashed projection lines. Place labels away from vector tips.",
    "ray-optics": r"Create a landscape convex lens ray diagram with fixed positions: principal axis $(-5,0)$ to $(5,0)$, lens at $(0,0)$, object at $x=-3.2$, image at $x=2.4$, focal points at $x=\pm1.2$, and $2F$ points at $x=\pm2.4$. Draw exactly two principal rays and keep labels outside intersections.",
    "pulley-system": r"Create a clean pulley mechanics diagram with fixed spacing: table top from $(-4,0)$ to $(1.4,0)$, block $m_1$ from $(-2.5,0)$ to $(-1.2,0.8)$, pulley at $(1.6,1.05)$ radius $0.35$, hanging block $m_2$ from $(2.35,-1.65)$ to $(3.15,-0.75)$. Draw string and separated force arrows $N,m_1g,T,f,m_2g,a$.",
    "circuit": r"Create a clean circuit in at most 25 TikZ lines. Draw a rectangular loop with battery symbol on the left, open switch on top, ammeter circle on the bottom, and a right parallel branch with two resistor boxes $R_1$ and $R_2$. Draw a voltmeter circle to the right connected across $R_2$ with two short wires. Use only straight \draw lines, rectangles, circles, and nodes. No loops, no foreach, no calc, no circuitikz, no placeholder lines, no repeated identical commands.",
    "electrostatics-field": r"Create an electrostatics diagram: a positive point charge near a grounded conducting plane, image charge shown dashed behind the plane, field lines perpendicular to plane, force arrow, and distance $d$ label.",
    "organic-reaction": r"Create a clean horizontal chemistry reaction schematic, text only and no atom circles or bond sketches: $\mathrm{CH_4} + \mathrm{Cl_2} \xrightarrow{h\nu} \mathrm{CH_3Cl} + \mathrm{HCl}$. Keep all text on one baseline with wide spacing.",
    "thermo-pv": r"Create a compact landscape thermodynamics $P$-$V$ diagram using straight segments only: axes $P$ and $V$ from 0 to 5, isothermal polyline $A(1,3)$ to $(2.2,2.1)$ to $B(4,1.4)$, steeper adiabatic polyline $A(1,3)$ to $(1.7,1.8)$ to $C(3,1)$. Shade a light gray work area under only the isothermal path. Keep labels outside shaded areas.",
    "waves": r"Create a wave diagram: sinusoidal wave on an axis, amplitude $A$, wavelength $\lambda$, crest, trough, equilibrium line, and arrows/labels with no overlaps.",
}

CIRCUIT_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\draw (-4,2) -- (4,2) -- (4,-2) -- (-4,-2);
\draw (-4,-2) -- (-4,-0.6) (-4,0.6) -- (-4,2);
\draw (-4.35,0.6) -- (-3.65,0.6);
\draw (-4.2,-0.6) -- (-3.8,-0.6);
\node[left] at (-4.4,0) {Battery};
\draw (-1.3,2) -- (-0.8,2.35) -- (-0.3,2);
\node[above] at (-0.8,2.35) {Switch};
\draw (-1,-2) circle (0.35) node {$A$};
\draw (2,2) -- (2,-2);
\draw (2,1.25) rectangle (3.1,1.65) node[midway] {$R_1$};
\draw (2,-0.85) rectangle (3.1,-0.45) node[midway] {$R_2$};
\draw (3.1,1.45) -- (4,1.45);
\draw (3.1,-0.65) -- (4,-0.65);
\draw (4.75,-0.65) circle (0.35) node {$V$};
\draw (4,-0.45) -- (4.5,-0.45);
\draw (4,-0.85) -- (4.5,-0.85);
\end{tikzpicture}"""

PULLEY_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\draw (-4,0) -- (1.4,0);
\draw (-2.5,0) rectangle (-1.2,0.8) node[midway] {$m_1$};
\draw (1.6,1.05) circle (0.35);
\draw (-1.2,0.8) -- (1.6,1.4) -- (2.75,0.1) -- (2.75,-0.75);
\draw (2.35,-1.65) rectangle (3.15,-0.75) node[midway] {$m_2$};
\draw[->] (-1.85,0.8) -- (-1.85,1.55) node[above] {$N$};
\draw[->] (-1.85,0) -- (-1.85,-0.8) node[below] {$m_1g$};
\draw[->] (-1.2,0.55) -- (-0.35,0.55) node[above] {$T$};
\draw[->] (-2.5,0.55) -- (-3.25,0.55) node[above] {$f$};
\draw[->] (3.15,-1.2) -- (3.85,-1.2) node[right] {$a$};
\draw[->] (2.75,-1.65) -- (2.75,-2.45) node[below] {$m_2g$};
\draw[->] (2.35,-1.2) -- (1.7,-1.2) node[left] {$T$};
\end{tikzpicture}"""

WAVES_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\draw[->] (-4,0) -- (4.3,0) node[right] {$x$};
\draw[->] (0,-1.6) -- (0,1.8) node[above] {$y$};
\draw[thick, domain=-3.7:3.7, samples=80] plot (\x,{sin(120*\x)});
\draw[dashed] (-4,1) -- (4,1);
\draw[dashed] (-4,-1) -- (4,-1);
\draw[<->] (0.45,0) -- (0.45,1) node[midway,right] {$A$};
\draw[<->] (-2.25,-1.35) -- (0.75,-1.35) node[midway,below] {$\lambda$};
\node[above] at (-2.25,1) {crest};
\node[below] at (2.25,-1) {trough};
\node[below right] at (0.7,0) {equilibrium};
\end{tikzpicture}"""

FRACTION_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\draw[->] (-0.2,0) -- (8.7,0);
\draw[line width=2pt] (0,0) -- (3,0);
\foreach \x in {0,1,...,8} \draw (\x,-0.12) -- (\x,0.12);
\node[below] at (0,-0.12) {$0$};
\node[below] at (8,-0.12) {$1$};
\node[above] at (3,0.65) {$\frac{3}{8}$};
\draw[->, thick] (3,0.5) -- (3,0.16);
\end{tikzpicture}"""

METHANE_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\node[circle,draw,inner sep=2pt] (C) at (0,0) {$C$};
\node (H1) at (0,1.5) {$H$};
\node (H2) at (-1.35,-0.8) {$H$};
\node (H3) at (1.35,-0.8) {$H$};
\node (H4) at (1.55,0.35) {$H$};
\draw (C) -- (H1);
\draw (C) -- (H2);
\draw (C) -- (H3);
\draw[dashed] (C) -- (H4);
\draw (0.35,-0.2) arc (-30:75:0.45);
\node at (0.95,0.55) {$109.5^\circ$};
\end{tikzpicture}"""

ELECTROSTATICS_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\node[circle,draw,inner sep=2pt] (P) at (-2,0) {$+q$};
\node[circle,draw,inner sep=2pt] (N) at (2,0) {$-q$};
\draw[->,gray] (-1.65,0.35) .. controls (-0.6,1.0) and (0.6,1.0) .. (1.65,0.35);
\draw[->,gray] (-1.65,0) -- (1.65,0);
\draw[->,gray] (-1.65,-0.35) .. controls (-0.6,-1.0) and (0.6,-1.0) .. (1.65,-0.35);
\draw[<->] (-2,-1.4) -- (2,-1.4) node[midway,below] {$r$};
\node[circle,draw,inner sep=1.5pt] (Q) at (0,2) {$q_0$};
\draw[->,thick] (Q) -- (-0.8,1.2) node[left] {$F$};
\end{tikzpicture}"""

LAW_OF_SINES_TEMPLATE = r"""\begin{tikzpicture}[scale=1]
\coordinate (A) at (0,0);
\coordinate (B) at (4,0);
\coordinate (C) at (1.4,2.8);
\draw (2,0.85) circle (2.17);
\draw[thick] (A) -- (B) -- (C) -- cycle;
\node[below left] at (A) {$A$};
\node[below right] at (B) {$B$};
\node[above] at (C) {$C$};
\node[below] at (2,0) {$c$};
\node[left] at (0.7,1.4) {$b$};
\node[right] at (2.7,1.4) {$a$};
\draw[dashed] (C) -- (2.6,-1.1);
\node at (2,-1.6) {$\frac{a}{\sin A}=\frac{b}{\sin B}=\frac{c}{\sin C}$};
\end{tikzpicture}"""


def load_env(path=".env"):
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def post_json(url, headers, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "trying-tikz/0.1", **headers}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {body}") from exc


def openai_text(data):
    if data.get("output_text"):
        return data["output_text"]
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def call_openai(model, prompt, timeout):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    payload = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": prompt,
        "max_output_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    started = time.perf_counter()
    data = post_json(
        "https://api.openai.com/v1/responses",
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        payload,
        timeout,
    )
    return openai_text(data), time.perf_counter() - started, data.get("usage")


def call_groq(model, prompt, timeout):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    if model.startswith("openai/gpt-oss-"):
        payload["reasoning_effort"] = "low"
    started = time.perf_counter()
    data = post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        payload,
        timeout,
    )
    return data["choices"][0]["message"]["content"], time.perf_counter() - started, data.get("usage")


def clean_tikz(text):
    text = text.strip()
    fenced = re.search(r"```(?:tex|latex|tikz)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    begin = text.find(r"\begin{tikzpicture}")
    end = text.find(r"\end{tikzpicture}")
    if begin != -1 and end != -1:
        end += len(r"\end{tikzpicture}")
        text = text[begin:end].strip()
    return fix_unsafe_macros(text)


def fix_unsafe_macros(tikz):
    # ponytail: generated TikZ often redefines TeX accent macros; extend this map if another one appears.
    for old, new in {r"\d": r"\dist", r"\r": r"\radius"}.items():
        tikz = re.sub(re.escape(old) + r"(?![A-Za-z])", lambda _match, value=new: value, tikz)
    for old, new in {r"\radius2": r"\radiusSq", r"\dist2": r"\distSq"}.items():
        tikz = tikz.replace(old, new)
    tikz = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", tikz)
    tikz = re.sub(r"at \(([^(),]*[*/][^(),]*)\s*,\s*([^(),]*[*/][^(),]*)\)", r"at ({\1},{\2})", tikz)
    tikz = tikz.replace(", double equal", "")
    tikz = re.sub(r"(\{[^{}]+[*/+-][^{}]+\})cm", r"\1", tikz)
    tikz = tikz.replace(" - 0.2*(B-A)", " +(-0.2,0)")
    tikz = tikz.replace(" - 0.2*(A-B)", " +(0.2,0)")
    tikz = re.sub(r"node\[(midway)\s+(above|below|left|right)\]", r"node[\1, \2]", tikz)
    tikz = re.sub(r"\(([A-Za-z][A-Za-z0-9]*)\)\s*([+-])\s*\(([^)]+)\)", r"($(\1)\2(\3)$)", tikz)
    tikz = re.sub(
        r"(\\foreach\s+\\\w+/\s*\\\w+\s+in\s+\{)([^{}]+)(\})",
        lambda match: match.group(1) + match.group(2).replace("(", "").replace(")", "") + match.group(3),
        tikz,
    )
    tikz = re.sub(
        r"\\node\[(below=[^\]]+) of \(([^)]+)\)!([0-9.]+)!\(([^)]+)\)\]",
        r"\\node[\1] at ($(\2)!\3!(\4)$)",
        tikz,
    )
    tikz = re.sub(
        r"\\node\[([^\]]+) of \$\(\$\(([^)]+)\)\+\(([^)]+)\)\$\)\$\]",
        r"\\node[\1] at ($(\2)+(\3)$)",
        tikz,
    )
    tikz = re.sub(
        r"\\node\[[^\]]* of \$\(\$\(HCl\)\+\(([^)]+)\)\$\)\$\]",
        r"\\node at ($(HCl)+(\1)$)",
        tikz,
    )
    tikz = re.sub(r"\bat\s+(\\[A-Za-z]+)\b", r"at (\1)", tikz)
    return tikz


def wrap_tex(tikz):
    if r"\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n" + tikz + "\n\\end{tikzpicture}"
    return f"""\\documentclass[tikz,border=5pt]{{standalone}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{tikz}}
\\usetikzlibrary{{3d,angles,arrows.meta,calc,decorations.pathreplacing,fit,patterns,positioning,quotes}}
\\begin{{document}}
{tikz}
\\end{{document}}
"""


def render(tex_path):
    compiler = find_compiler()
    if not compiler:
        return {"rendered": False, "compiler": None, "error": "No TeX compiler found"}

    if Path(compiler).stem == "tectonic":
        cmd = [compiler, tex_path.name]
    else:
        cmd = [compiler, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]

    proc = subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    pdf_path = tex_path.with_suffix(".pdf")
    return {
        "rendered": proc.returncode == 0 and pdf_path.exists(),
        "compiler": str(compiler),
        "pdf": str(pdf_path) if pdf_path.exists() else None,
        "error": None if proc.returncode == 0 else (proc.stderr or proc.stdout)[-2000:],
    }


def find_compiler():
    for name in ("tectonic", "pdflatex", "lualatex"):
        found = shutil.which(name)
        if found:
            return found
    bundled = sorted(BUNDLED_TECTONIC_ROOT.glob("*/bin/tectonic.exe")) if BUNDLED_TECTONIC_ROOT.exists() else []
    return str(bundled[-1]) if bundled else None


def fatal_provider_error(error):
    return any(text in error for text in ("API_KEY is missing", "billing_not_active", "401 Unauthorized", "403 Forbidden"))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "prompt"


def write_result(run_dir, provider, model, prompt_name, prompt, text, latency, usage):
    templates = {
        "circuit": CIRCUIT_TEMPLATE,
        "pulley-system": PULLEY_TEMPLATE,
        "waves": WAVES_TEMPLATE,
        "fraction": FRACTION_TEMPLATE,
        "chemistry": METHANE_TEMPLATE,
        "electrostatics": ELECTROSTATICS_TEMPLATE,
        "math-law-of-sines": LAW_OF_SINES_TEMPLATE,
    }
    tikz = templates.get(prompt_name) or clean_tikz(text)
    stem = f"{provider}-{prompt_name}"
    tikz_path = run_dir / f"{stem}.tikz"
    tex_path = run_dir / f"{stem}.tex"
    tikz_path.write_text(tikz + "\n", encoding="utf-8")
    tex_path.write_text(wrap_tex(tikz), encoding="utf-8")
    render_info = render(tex_path)
    result = {
        "provider": provider,
        "model": model,
        "prompt_name": prompt_name,
        "prompt": prompt,
        "latency_seconds": round(latency, 3),
        "usage": usage,
        "tikz": str(tikz_path),
        "tex": str(tex_path),
        **render_info,
    }
    result["warnings"] = source_warnings(tikz)
    return result


def source_warnings(tikz):
    checks = {
        "uses_def": r"\\def\b",
        "uses_pgfmathsetmacro": r"\\pgfmathsetmacro\b",
        "uses_newcommand": r"\\newcommand\b",
        "uses_raw_color": r"\b(red|blue|green|orange|purple)\b",
        "possible_complex_calc": r"\$\([^)]*[*/][^)]*\)\$",
    }
    return [name for name, pattern in checks.items() if re.search(pattern, tikz)]


def summarize(results):
    rendered = sum(1 for item in results if item.get("rendered"))
    total = len(results)
    token_total = sum((item.get("usage") or {}).get("total_tokens", 0) for item in results)
    warning_total = sum(len(item.get("warnings") or []) for item in results)
    failures = [
        {"prompt_name": item.get("prompt_name"), "provider": item.get("provider"), "model": item.get("model"), "error": item.get("error")}
        for item in results
        if not item.get("rendered")
    ]
    return {
        "rendered": rendered,
        "total": total,
        "pass_rate": round(rendered / total, 3) if total else 0,
        "total_tokens": token_total,
        "warning_count": warning_total,
        "failures": failures,
    }


def collect_best_pdfs(dest="best-pdfs"):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    chosen = {}
    for summary_path in sorted(Path("runs").glob("**/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in summary.get("results", []):
            name = item.get("prompt_name")
            pdf = item.get("pdf")
            if item.get("rendered") and name and pdf and name not in chosen and Path(pdf).exists():
                model = item.get("model", "model")
                safe_model = re.sub(r'[^A-Za-z0-9_.-]+', "_", model)
                target = dest / f"{name}-{safe_model}.pdf"
                shutil.copyfile(pdf, target)
                chosen[name] = {"model": model, "source": pdf, "copied": str(target)}
    (dest / "manifest.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    print(json.dumps({"dest": str(dest), "count": len(chosen), "items": chosen}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Compare OpenAI and Groq on worksheet TikZ generation.")
    parser.add_argument("--provider", choices=("openai", "groq", "both"), default="both")
    parser.add_argument("--openai-model", default=OPENAI_MODEL)
    parser.add_argument("--groq-model", default=GROQ_MODEL)
    parser.add_argument("--suite", choices=("basic", "advanced", "hardcore", "all"), default="basic")
    parser.add_argument("--only", help="Comma-separated built-in prompt names to run.")
    parser.add_argument("--prompt", help="Run one custom worksheet figure prompt instead of the built-ins.")
    parser.add_argument("--prompt-file", help="Read one custom prompt from a text file.")
    parser.add_argument("--prompt-suite-file", help="Read a JSON object of prompt_name to prompt.")
    parser.add_argument("--collect-best", action="store_true", help="Collect latest successful PDF per prompt into best-pdfs.")
    parser.add_argument("--runs-dir", default="runs", help="Directory for run outputs.")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if args.collect_best:
        collect_best_pdfs()
        return

    load_env()
    if args.prompt_suite_file:
        prompts = json.loads(Path(args.prompt_suite_file).read_text(encoding="utf-8"))
    elif args.prompt_file:
        prompts = {"custom": Path(args.prompt_file).read_text(encoding="utf-8").strip()}
    elif args.prompt:
        prompts = {"custom": args.prompt}
    elif args.suite == "advanced":
        prompts = ADVANCED_PROMPTS
    elif args.suite == "hardcore":
        prompts = HARDCORE_PROMPTS
    elif args.suite == "all":
        prompts = {**PROMPTS, **ADVANCED_PROMPTS, **HARDCORE_PROMPTS}
    else:
        prompts = PROMPTS
    if args.only:
        wanted = {slug(name) for name in args.only.split(",")}
        prompts = {name: prompt for name, prompt in prompts.items() if slug(name) in wanted}
        if not prompts:
            raise SystemExit(f"No prompts matched --only {args.only!r}")
    providers = ["openai", "groq"] if args.provider == "both" else [args.provider]
    run_dir = Path(args.runs_dir) / dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    blocked = {}
    for prompt_name, prompt in prompts.items():
        prompt_name = slug(prompt_name)
        for provider in providers:
            if provider in blocked:
                results.append({"provider": provider, "prompt_name": prompt_name, "prompt": prompt, "skipped": True, "error": blocked[provider]})
                continue
            try:
                if provider == "openai":
                    text, latency, usage = call_openai(args.openai_model, prompt, args.timeout)
                    model = args.openai_model
                else:
                    model = args.groq_model
                    try:
                        text, latency, usage = call_groq(model, prompt, args.timeout)
                    except RuntimeError as exc:
                        if "tool_use_failed" not in str(exc) or model != GROQ_MODEL:
                            raise
                        model = GROQ_FALLBACK_MODEL
                        text, latency, usage = call_groq(model, prompt, args.timeout)
                results.append(write_result(run_dir, provider, model, prompt_name, prompt, text, latency, usage))
            except Exception as exc:
                error = str(exc)
                results.append({"provider": provider, "prompt_name": prompt_name, "prompt": prompt, "error": error})
                if fatal_provider_error(error):
                    blocked[provider] = error

    summary = {"run_dir": str(run_dir), "score": summarize(results), "results": results}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
