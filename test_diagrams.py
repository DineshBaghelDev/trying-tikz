"""Interactive launcher for the diagram generation harness."""

import json
import subprocess
import sys
from pathlib import Path

from tikz_harness import core


ROOT = Path(__file__).resolve().parent


def choose(title, options, default=0):
    print(f"\n{title}")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        value = input(f"Choose [{default + 1}]: ").strip()
        if not value:
            return default
        if value.isdigit() and 1 <= int(value) <= len(options):
            return int(value) - 1
        print(f"Enter a number from 1 to {len(options)}.")


def prompt_suites():
    suites = []
    for path in sorted(ROOT.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data and all(isinstance(value, str) for value in data.values()):
            suites.append((path, data))
    return suites


def select_prompts():
    suites = prompt_suites()
    options = ["Built-in basic", "Built-in advanced", "Built-in all", "One custom prompt"]
    options.extend(f"{path.name} ({len(data)} prompts)" for path, data in suites)
    selected = choose("Prompt source", options)
    if selected < 3:
        suite = ("basic", "advanced", "all")[selected]
        prompts = core.PROMPTS if suite == "basic" else core.ADVANCED_PROMPTS
        if suite == "all":
            prompts = {**core.PROMPTS, **core.ADVANCED_PROMPTS}
        args = ["--suite", suite]
    elif selected == 3:
        return ["--prompt", input("Prompt: ").strip()]
    else:
        path, prompts = suites[selected - 4]
        args = ["--prompt-suite-file", str(path)]

    names = list(prompts)
    print("\nPrompts")
    print("  0. All prompts")
    for index, name in enumerate(names, 1):
        print(f"  {index}. {name}: {prompts[name][:80]}")
    while True:
        raw = input("Choose 0, one number, or comma-separated numbers: ").strip()
        if raw == "0":
            return args
        try:
            indexes = [int(value.strip()) for value in raw.split(",")]
            if indexes and all(1 <= index <= len(names) for index in indexes):
                chosen = [names[index - 1] for index in indexes]
                return args + ["--only", ",".join(chosen)]
        except ValueError:
            pass
        print("Enter 0 or valid prompt numbers, for example 1,3,5.")


def select_models():
    mode = choose("What do you want to do?", [
        "Generate diagrams with one model (recommended)",
        "Compare models using the same prompts",
        "Use an external model-matrix file (advanced)",
    ])
    if mode == 0:
        provider = ("groq", "openai")[choose("Provider", ["Groq", "OpenAI"])]
        if provider == "groq":
            models = [
                ("openai/gpt-oss-20b", "GPT-OSS 20B - fast and inexpensive"),
                ("qwen/qwen3-32b", "Qwen 3 32B - stronger diagram planning"),
                ("openai/gpt-oss-120b", "GPT-OSS 120B - larger and slower"),
            ]
        else:
            models = [(core.OPENAI_MODEL, f"Default OpenAI model - {core.OPENAI_MODEL}")]
        selected = choose("Model", [label for _, label in models] + ["Enter another model ID"])
        model = models[selected][0] if selected < len(models) else input("Exact model ID: ").strip()
        if not model:
            raise SystemExit("A model ID is required.")
        flag = "--groq-models" if provider == "groq" else "--openai-model"
        return ["--provider", provider, flag, model]
    if mode == 1:
        recommended = "openai/gpt-oss-20b,qwen/qwen3-32b,openai/gpt-oss-120b"
        selection = choose("Models to compare", [
            "Recommended Groq set (3 models)",
            "Enter my own comma-separated Groq model IDs",
        ])
        models = recommended if selection == 0 else input("Model IDs separated by commas: ").strip()
        if not models:
            raise SystemExit("At least one model ID is required.")
        print("Each selected model will receive exactly the same prompts.")
        return ["--provider", "groq", "--groq-models", models]

    configs = sorted(ROOT.glob("*model*.json"))
    if not configs:
        raise SystemExit("No model configuration JSON file was found.")
    config = configs[choose("Model matrix", [path.name for path in configs])]
    return ["--provider", "none", "--model-config", str(config)]


def main():
    print("Deterministic Diagram Harness")
    cli = [sys.executable, str(ROOT / "try_tikz.py")]
    command = list(cli)
    command.extend(select_models())

    pipeline_values = ["deterministic", "vision", "templates", "plain", "compare all pipelines"]
    pipeline_labels = [
        "Deterministic - model writes JSON; SymPy validates geometry (recommended)",
        "Vision - model draws TikZ and a vision model reviews it",
        "Templates - model draws TikZ using a similar example",
        "Plain - model draws TikZ directly",
        "Compare all pipelines - slowest; runs every method",
    ]
    pipeline = pipeline_values[choose("How should diagrams be generated?", pipeline_labels)]
    if pipeline == "compare all pipelines":
        command.append("--compare")
    else:
        command.extend(["--pipeline", pipeline])

    command.extend(select_prompts())
    retries = input("Compile/spec repair retries [1]: ").strip() or "1"
    runs_dir = ROOT / "runs" / "interactive"
    command.extend(["--retries", retries, "--runs-dir", str(runs_dir)])
    make_sheet = input("Create/update contact sheets after the run? [Y/n]: ").strip().lower() != "n"

    print("\nRunning:")
    print(subprocess.list2cmdline(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode or not make_sheet or "--compare" in command:
        raise SystemExit(result.returncode)

    best_dir = ROOT / "runs" / "interactive-best"
    review_dir = ROOT / "runs" / "interactive-review"
    collect = cli + ["--collect-best", "--by-model", "--runs-dir", str(runs_dir), "--best-dir", str(best_dir)]
    sheet = cli + ["--contact-sheet", "--best-dir", str(best_dir), "--review-dir", str(review_dir)]
    if subprocess.run(collect, cwd=ROOT).returncode == 0:
        if subprocess.run(sheet, cwd=ROOT).returncode == 0:
            print(f"\nContact sheets: {review_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
