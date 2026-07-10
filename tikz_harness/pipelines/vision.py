import json
from pathlib import Path

from tikz_harness import core


def run(run_dir, provider, model, prompt_name, prompt, timeout, retries, vision_model, critique):
    results = []
    enriched_prompt = core.enrich_prompt(prompt)
    blueprint, blueprint_warnings = None, []
    try:
        model, (bp_text, _, _) = core._call_with_fallback(
            provider, model, enriched_prompt, timeout, core.BLUEPRINT_SYSTEM_PROMPT)
        blueprint = core.parse_json_loose(bp_text)
        blueprint_warnings = core.lint_blueprint(blueprint)
    except (RuntimeError, json.JSONDecodeError, ValueError):
        blueprint = None

    if blueprint is not None:
        model, (text, latency, usage) = core._call_with_fallback(
            provider, model, core.code_input(blueprint), timeout, core.CODE_SYSTEM_PROMPT)
    else:
        model, (text, latency, usage) = core._call_with_fallback(
            provider, model, enriched_prompt, timeout, core.SYSTEM_PROMPT)

    result, stage_results = core._compile_with_repairs(
        run_dir, provider, model, prompt_name, prompt, timeout, retries,
        text, (latency, usage), blueprint, blueprint_warnings, "a")
    results.extend(stage_results)
    if not result["rendered"]:
        return results

    best = result
    for i in range(critique):
        try:
            crit = core.vision_critique(vision_model, best["pdf"], enriched_prompt, timeout)
        except Exception as exc:
            best.setdefault("vision", {"error": str(exc)[:200]})
            break
        if crit is None:
            break
        best["vision"] = crit
        best["score"] = core.score(best)
        good = isinstance(crit.get("score"), (int, float)) and crit["score"] >= 8 and not crit.get("overlaps")
        if good or i == critique - 1:
            break
        if blueprint is not None:
            try:
                model, (bp_text, _, _) = core._call_with_fallback(
                    provider, model, core.blueprint_repair_prompt(enriched_prompt, blueprint, crit),
                    timeout, core.BLUEPRINT_SYSTEM_PROMPT)
                blueprint = core.parse_json_loose(bp_text)
                blueprint_warnings = core.lint_blueprint(blueprint)
            except (RuntimeError, json.JSONDecodeError, ValueError):
                pass
            model, (text, latency, usage) = core._call_with_fallback(
                provider, model, core.code_input(blueprint), timeout, core.CODE_SYSTEM_PROMPT)
        else:
            model, (text, latency, usage) = core._call_with_fallback(
                provider, model, core.polish_prompt(enriched_prompt, Path(best["tikz"]).read_text(encoding="utf-8")),
                timeout, core.SYSTEM_PROMPT)
        candidate, cand_results = core._compile_with_repairs(
            run_dir, provider, model, prompt_name, prompt, timeout, retries,
            text, (latency, usage), blueprint, blueprint_warnings, f"c{i + 1}")
        results.extend(cand_results)
        if candidate["rendered"]:
            best = candidate
    return results
