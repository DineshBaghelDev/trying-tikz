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
BUNDLED_TECTONIC_ROOT = Path.home() / ".codex" / "plugins" / "cache" / "openai-bundled" / "latex"

SYSTEM_PROMPT = """You generate worksheet-ready TikZ figures.
Return only TikZ code. Prefer a complete \\begin{tikzpicture}...\\end{tikzpicture}.
Use clear labels, simple black-and-white styling, and code that compiles in a standalone LaTeX document.
Prefer explicit numeric coordinates over \\def or \\pgfmathsetmacro calculations."""

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
        "max_output_tokens": 1200,
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
        "max_completion_tokens": 1200,
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
    tikz = tikz.replace(", double equal", "")
    tikz = re.sub(r"(\{[^{}]+[*/+-][^{}]+\})cm", r"\1", tikz)
    tikz = tikz.replace(" - 0.2*(B-A)", " +(-0.2,0)")
    tikz = tikz.replace(" - 0.2*(A-B)", " +(0.2,0)")
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
    tikz = re.sub(r"\bat\s+(\\[A-Za-z]+)\b", r"at (\1)", tikz)
    return tikz


def wrap_tex(tikz):
    if r"\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n" + tikz + "\n\\end{tikzpicture}"
    return f"""\\documentclass[tikz,border=5pt]{{standalone}}
\\usepackage{{amsmath}}
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

    proc = subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, text=True, timeout=60)
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
    tikz = clean_tikz(text)
    stem = f"{provider}-{prompt_name}"
    tikz_path = run_dir / f"{stem}.tikz"
    tex_path = run_dir / f"{stem}.tex"
    tikz_path.write_text(tikz + "\n", encoding="utf-8")
    tex_path.write_text(wrap_tex(tikz), encoding="utf-8")
    render_info = render(tex_path)
    return {
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


def main():
    parser = argparse.ArgumentParser(description="Compare OpenAI and Groq on worksheet TikZ generation.")
    parser.add_argument("--provider", choices=("openai", "groq", "both"), default="both")
    parser.add_argument("--openai-model", default=OPENAI_MODEL)
    parser.add_argument("--groq-model", default=GROQ_MODEL)
    parser.add_argument("--suite", choices=("basic", "advanced", "all"), default="basic")
    parser.add_argument("--prompt", help="Run one custom worksheet figure prompt instead of the built-ins.")
    parser.add_argument("--prompt-file", help="Read one custom prompt from a text file.")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    load_env()
    if args.prompt_file:
        prompts = {"custom": Path(args.prompt_file).read_text(encoding="utf-8").strip()}
    elif args.prompt:
        prompts = {"custom": args.prompt}
    elif args.suite == "advanced":
        prompts = ADVANCED_PROMPTS
    elif args.suite == "all":
        prompts = {**PROMPTS, **ADVANCED_PROMPTS}
    else:
        prompts = PROMPTS
    providers = ["openai", "groq"] if args.provider == "both" else [args.provider]
    run_dir = Path("runs") / dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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

    summary = {"run_dir": str(run_dir), "results": results}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
