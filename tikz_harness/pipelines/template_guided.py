from tikz_harness import core


def run(run_dir, provider, model, prompt_name, prompt, timeout, retries):
    model, detailed_prompt, brief_latency, brief_usage = core.expand_diagram_prompt(provider, model, prompt, timeout)
    retrieved = core.retrieve_template(prompt + "\n" + detailed_prompt)
    if retrieved:
        name, template, method, sim = retrieved
    else:
        name, template, method, sim = None, None, "none", 0.0
    user_prompt = core.templates_prompt(prompt, detailed_prompt, template)
    model, (text, latency, usage) = core._call_with_fallback(provider, model, user_prompt, timeout, core.SYSTEM_PROMPT)
    _, results = core._compile_with_repairs(
        run_dir, provider, model, prompt_name, prompt, timeout,
        retries, text, (latency, usage), None, [], "a")
    for item in results:
        item["expanded_prompt"] = detailed_prompt
        item["template"] = {"name": name, "method": method, "similarity": sim}
        item["brief_usage"] = brief_usage
        item["brief_latency_seconds"] = round(brief_latency, 3)
    return results

