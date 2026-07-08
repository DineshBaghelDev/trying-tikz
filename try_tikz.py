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

SYSTEM_PROMPT = """You generate worksheet-ready TikZ figures.
Return only TikZ code. Prefer a complete \\begin{tikzpicture}...\\end{tikzpicture}.
Use clear labels, simple black-and-white styling, and code that compiles in a standalone LaTeX document."""

PROMPTS = {
    "geometry": "Create a labeled triangle ABC with side lengths 5 cm, 6 cm, 7 cm and one marked angle at A.",
    "coordinate": "Create a coordinate plane with grid, axes, points A(-2,1) and B(3,4), and the segment AB.",
    "fraction": "Create a number line from 0 to 1 split into eighths, with 3/8 shaded or emphasized.",
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
    }
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
        return text[begin:end].strip()
    return text


def wrap_tex(tikz):
    if r"\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n" + tikz + "\n\\end{tikzpicture}"
    return f"""\\documentclass[tikz,border=5pt]{{standalone}}
\\usepackage{{tikz}}
\\usetikzlibrary{{angles,arrows.meta,calc,patterns,positioning,quotes}}
\\begin{{document}}
{tikz}
\\end{{document}}
"""


def render(tex_path):
    compiler = next((name for name in ("tectonic", "pdflatex", "lualatex") if shutil.which(name)), None)
    if not compiler:
        return {"rendered": False, "compiler": None, "error": "No TeX compiler found on PATH"}

    if compiler == "tectonic":
        cmd = [compiler, tex_path.name]
    else:
        cmd = [compiler, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]

    proc = subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, text=True, timeout=60)
    pdf_path = tex_path.with_suffix(".pdf")
    return {
        "rendered": proc.returncode == 0 and pdf_path.exists(),
        "compiler": compiler,
        "pdf": str(pdf_path) if pdf_path.exists() else None,
        "error": None if proc.returncode == 0 else (proc.stderr or proc.stdout)[-2000:],
    }


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
    parser.add_argument("--prompt", help="Run one custom worksheet figure prompt instead of the built-ins.")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    load_env()
    prompts = {"custom": args.prompt} if args.prompt else PROMPTS
    providers = ["openai", "groq"] if args.provider == "both" else [args.provider]
    run_dir = Path("runs") / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for prompt_name, prompt in prompts.items():
        prompt_name = slug(prompt_name)
        for provider in providers:
            try:
                if provider == "openai":
                    text, latency, usage = call_openai(args.openai_model, prompt, args.timeout)
                    model = args.openai_model
                else:
                    text, latency, usage = call_groq(args.groq_model, prompt, args.timeout)
                    model = args.groq_model
                results.append(write_result(run_dir, provider, model, prompt_name, prompt, text, latency, usage))
            except Exception as exc:
                results.append({"provider": provider, "prompt_name": prompt_name, "prompt": prompt, "error": str(exc)})

    summary = {"run_dir": str(run_dir), "results": results}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
