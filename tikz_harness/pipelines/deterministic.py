"""Adaptive quality pipeline: exact geometry where useful, domain guidance elsewhere."""

import json

from tikz_harness import core, deterministic
from tikz_harness.pipelines import template_guided, vision


EXACT_MATH = (
    "altitude", "orthocenter", "median", "centroid", "angle-bisector",
    "coordinate-distance", "circle-tangent", "3d-cuboid",
)
TRUSTED_TEMPLATES = (
    (("benzene", "aromatic ring"), "chem-benzene-aromatic"),
    (("inclined plane", "block on a ramp", "block on an inclined"), "physics-inclined-plane"),
    (("convex lens",), "physics-convex-lens"),
    (("simple pendulum",), "physics-simple-pendulum"),
    (("spring-mass", "spring mass"), "physics-spring-mass"),
)


def choose_route(prompt_name, prompt):
    """Choose the narrowest engine likely to preserve the prompt's semantics."""
    text = prompt.lower()
    for phrases, name in TRUSTED_TEMPLATES:
        if any(phrase in text for phrase in phrases):
            return "trusted-template", name
    if prompt_name.startswith("math-") and any(key in prompt_name for key in EXACT_MATH):
        return "exact", "exact geometric construction"
    retrieved = core.retrieve_template(prompt)
    if retrieved and retrieved[3] >= 0.18:
        return "template", f"matched domain template {retrieved[0]}"
    return "vision", "specialist or illustrative diagram"


def _repair_prompt(prompt, spec, errors, critique=None):
    visual = f"\nRendered-image critique:\n{json.dumps(critique, indent=2)}\n" if critique else ""
    return f"""Repair this deterministic diagram specification.

Original request:
{prompt}

Validation errors:
{json.dumps(errors)}
{visual}
Current specification:
{json.dumps(spec, indent=2)}

Preserve valid geometry. Change only invalid references, unsupported fields, or visual layout.
Return only a corrected JSON object using the required schema.
"""


def _annotate(results, route, reason):
    for result in results:
        result["adaptive"] = {"route": route, "reason": reason}
    return results


def _best(results):
    return max(results, key=lambda item: item.get("score", -100), default=None)


def _review(result, vision_model, prompt, timeout):
    if not result or not result.get("rendered") or not result.get("pdf"):
        return None
    try:
        critique = core.vision_critique(vision_model, result["pdf"], prompt, timeout)
    except Exception as exc:
        result["vision"] = {"error": str(exc)[:200]}
        return None
    if critique:
        result["vision"] = critique
        result["score"] = core.score(result)
    return critique


def _needs_fallback(result, critique):
    if not result or not result.get("rendered"):
        return True
    if critique is None:
        return False
    return critique.get("score", 0) < 8 or critique.get("overlaps") or not critique.get("geometry_correct", True)


def _fallback(run_dir, provider, model, prompt_name, prompt, timeout, retries,
              vision_model, critique, results, reason):
    fallback = vision.run(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                          vision_model, max(2, critique))
    return results + _annotate(fallback, "vision-fallback", reason)


def _run_exact(run_dir, provider, model, prompt_name, prompt, timeout, retries,
               vision_model, critique_limit, reason):
    results = []
    request, spec = prompt, {}
    for attempt in range(retries + 1):
        model, (text, latency, usage) = core._call_with_fallback(
            provider, model, request, timeout, deterministic.SPEC_SYSTEM_PROMPT)
        try:
            spec = core.parse_json_loose(text)
            tikz, _, hard = deterministic.render(spec)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError) as exc:
            results.append({
                "provider": provider, "model": model, "prompt_name": prompt_name,
                "prompt": prompt, "attempt": f"d{attempt}", "latency_seconds": round(latency, 3),
                "usage": usage, "rendered": False, "error": str(exc), "score": -100,
                "adaptive": {"route": "exact", "reason": reason},
            })
            request = _repair_prompt(prompt, spec, [str(exc)])
            continue

        result = core.write_candidate(run_dir, provider, model, prompt_name, prompt, tikz, latency,
                                      usage, f"d{attempt}", spec, [])
        result["deterministic"] = deterministic.quality_metrics(spec)
        result["hardness"] = hard
        result["adaptive"] = {"route": "exact", "reason": reason}
        result["score"] = core.score(result)
        results.append(result)
        if result.get("rendered"):
            break
        request = _repair_prompt(prompt, spec, [result.get("error")])

    best = _best(results)
    review = _review(best, vision_model, prompt, timeout)
    if best and review and _needs_fallback(best, review) and critique_limit:
        request = _repair_prompt(prompt, spec, [], review)
        model, (text, latency, usage) = core._call_with_fallback(
            provider, model, request, timeout, deterministic.SPEC_SYSTEM_PROMPT)
        try:
            revised = core.parse_json_loose(text)
            tikz, _, hard = deterministic.render(revised)
            candidate = core.write_candidate(run_dir, provider, model, prompt_name, prompt, tikz,
                                             latency, usage, "dv0", revised, [])
            candidate["deterministic"] = deterministic.quality_metrics(revised)
            candidate["hardness"] = hard
            candidate["adaptive"] = {"route": "exact-visual-repair", "reason": review.get("fix_hint")}
            candidate["score"] = core.score(candidate)
            results.append(candidate)
            best = candidate if candidate.get("rendered") else best
            review = _review(best, vision_model, prompt, timeout)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            pass
    if _needs_fallback(best, review):
        return _fallback(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                         vision_model, critique_limit, results, "exact route failed quality gate")
    return results


def run(run_dir, provider, model, prompt_name, prompt, timeout, retries, vision_model, critique):
    route, reason = choose_route(prompt_name, prompt)
    if route == "exact":
        return _run_exact(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                          vision_model, critique, reason)
    if route == "vision":
        return _annotate(vision.run(run_dir, provider, model, prompt_name, prompt, timeout,
                                    retries, vision_model, max(2, critique)), route, reason)

    if route == "trusted-template":
        template = core.templates_mod.TEMPLATES[reason]
        result = core.write_candidate(run_dir, provider, model, prompt_name, prompt,
                                      template["tikz"], 0, None, "t0", None, [])
        results = _annotate([result], route, f"trusted domain template {reason}")
        review = _review(result, vision_model, prompt, timeout)
        if _needs_fallback(result, review):
            return _fallback(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                             vision_model, critique, results, "trusted template missed quality requirements")
        return results

    results = _annotate(template_guided.run(run_dir, provider, model, prompt_name, prompt,
                                            timeout, retries), route, reason)
    best = _best(results)
    review = _review(best, vision_model, prompt, timeout)
    if _needs_fallback(best, review):
        return _fallback(run_dir, provider, model, prompt_name, prompt, timeout, retries,
                         vision_model, critique, results, "template route failed quality gate")
    return results
