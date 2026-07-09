from tikz_harness import core


def run(run_dir, provider, model, prompt_name, prompt, timeout, retries):
    model, (text, latency, usage) = core._call_with_fallback(provider, model, prompt, timeout, core.SYSTEM_PROMPT)
    _, results = core._compile_with_repairs(
        run_dir, provider, model, prompt_name, prompt, timeout,
        retries, text, (latency, usage), None, [], "a")
    return results

