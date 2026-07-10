"""Interactive launcher for the diagram generation harness."""

import json
import subprocess
import sys
from pathlib import Path

from tikz_harness import core


ROOT = Path(__file__).resolve().parent


def choose(title, options):
    print(f"\n{title}")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        value = input("Choose: ").strip()
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
    architecture = choose("Test architecture", ["Single model", "Multiple Groq models", "External model matrix"])
    if architecture == 0:
        provider = ("groq", "openai")[choose("Provider", ["Groq", "OpenAI"])]
        default = core.GROQ_MODEL if provider == "groq" else core.OPENAI_MODEL
        model = input(f"Model [{default}]: ").strip() or default
        flag = "--groq-models" if provider == "groq" else "--openai-model"
        return ["--provider", provider, flag, model]
    if architecture == 1:
        default = core.GROQ_TEXT_MODELS
        models = input(f"Comma-separated models [{default}]: ").strip() or default
        return ["--provider", "groq", "--groq-models", models]

    configs = sorted(ROOT.glob("*model*.json"))
    if not configs:
        raise SystemExit("No model configuration JSON file was found.")
    config = configs[choose("Model matrix", [path.name for path in configs])]
    return ["--provider", "none", "--model-config", str(config)]


def main():
    print("Deterministic Diagram Harness")
    command = [sys.executable, str(ROOT / "try_tikz.py")]
    command.extend(select_models())

    pipelines = ["deterministic", "plain", "templates", "vision", "compare all pipelines"]
    pipeline = pipelines[choose("Pipeline", pipelines)]
    if pipeline == "compare all pipelines":
        command.append("--compare")
    else:
        command.extend(["--pipeline", pipeline])

    command.extend(select_prompts())
    retries = input("Compile/spec repair retries [1]: ").strip() or "1"
    command.extend(["--retries", retries, "--runs-dir", str(ROOT / "runs" / "interactive")])

    print("\nRunning:")
    print(subprocess.list2cmdline(command))
    raise SystemExit(subprocess.run(command, cwd=ROOT).returncode)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
