import json

from tikz_harness import core, deterministic


def _repair_prompt(prompt, spec, errors):
    return f"""Repair this deterministic diagram specification.

Original request:
{prompt}

Validation errors:
{json.dumps(errors)}

Current specification:
{json.dumps(spec, indent=2)}

Return only a corrected JSON object using the required schema.
"""


def run(run_dir, provider, model, prompt_name, prompt, timeout, retries):
    results = []
    request = prompt
    for attempt in range(retries + 1):
        model, (text, latency, usage) = core._call_with_fallback(
            provider, model, request, timeout, deterministic.SPEC_SYSTEM_PROMPT)
        try:
            spec = core.parse_json_loose(text)
            tikz, validation, hard = deterministic.render(spec)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError) as exc:
            result = {
                "provider": provider, "model": model, "prompt_name": prompt_name,
                "prompt": prompt, "attempt": f"d{attempt}", "latency_seconds": round(latency, 3),
                "usage": usage, "rendered": False, "error": str(exc), "score": -100,
            }
            results.append(result)
            if attempt == retries:
                break
            request = _repair_prompt(prompt, locals().get("spec", {}), [str(exc)])
            continue

        result = core.write_candidate(
            run_dir, provider, model, prompt_name, prompt, tikz, latency, usage,
            f"d{attempt}", spec, [])
        result["deterministic"] = deterministic.quality_metrics(spec)
        result["hardness"] = hard
        result["score"] = core.score(result)
        results.append(result)
        break
    return results
