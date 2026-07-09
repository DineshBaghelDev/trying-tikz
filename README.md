# trying-tikz

Tiny Python harness for testing worksheet-style TikZ generation with OpenAI and Groq.

The CLI is still `try_tikz.py`, but the code now lives under `tikz_harness/` so pipelines can be swapped without mixing experiments into one file.

## Layout

- `try_tikz.py` - thin compatibility CLI shim.
- `tikz_harness/core.py` - shared provider calls, rendering, scoring, prompt loading, suite runner, and review-sheet helpers.
- `tikz_harness/pipelines/plain.py` - direct prompt to TikZ.
- `tikz_harness/pipelines/template_guided.py` - first-pass drawing brief, template exemplar, then fresh TikZ.
- `tikz_harness/pipelines/vision.py` - blueprint/code/render/vision-critique loop.
- `tikz_harness/templates/library.py` - few-shot TikZ exemplars only; no locked/direct templates.
- `test_harness.py` - offline functional checks.

## Setup

Put keys in `.env`:

```text
OPENAI_API_KEY=...
GROQ_API_KEY=...
```

## Run

Basic smoke test:

```powershell
python try_tikz.py --provider groq
```

Class 5-12 math/science examples:

```powershell
python try_tikz.py --provider groq --suite advanced --groq-models qwen/qwen3-32b --pipeline templates --retries 2 --runs-dir runs\student-smoke
```

Your own prompt:

```powershell
python try_tikz.py --provider groq --prompt 'Draw a convex lens ray diagram with object, image, focal points, and two clean rays.'
```

PowerShell expands `$O` inside double quotes, so use single quotes for LaTeX-style math.

Run a JSON suite:

```powershell
python try_tikz.py --provider groq --prompt-suite-file stress_prompts_90.json --groq-models qwen/qwen3-32b --pipeline templates --retries 2 --runs-dir runs\stress-90
```

Pipeline choices:

- `--pipeline plain` - one model call, then compile/repair.
- `--pipeline templates` - expand the prompt into a drawing brief, inject the nearest exemplar, then compile/repair.
- `--pipeline vision` - JSON spatial blueprint, TikZ generation, and optional rendered-image critique.

## Outputs

Each run writes to `runs/<timestamp>/` or the folder passed with `--runs-dir`:

- `.tikz` cleaned model output
- `.tex` standalone wrapper
- `.pdf` when a compiler is available
- `summary.json` with model, latency, token usage, render status, warnings, and source stats

Collect latest successful PDFs and make a review sheet:

```powershell
python try_tikz.py --collect-best --runs-dir runs\student-smoke --best-dir runs\student-smoke-best
python try_tikz.py --contact-sheet --best-dir runs\student-smoke-best --review-dir runs\student-smoke-review
```

## Rendering

The script tries `tectonic`, then `pdflatex`, then `lualatex`, then Codex's bundled Tectonic. If none are available, it still writes `.tikz` and `.tex` and records `"rendered": false`.

For local PDFs outside Codex:

```powershell
winget install Tectonic.Tectonic
```

## Production Note

For a worksheet generator, do not trust raw model output blindly. Use this flow:

1. Generate TikZ.
2. Compile.
3. Retry once or twice with compiler feedback.
4. Review PDFs/contact sheets before shipping.

That is the cheap path to good figures without hardcoding every topic.

For 95%+ production confidence, keep this model-first path for uncommon diagrams, but add deterministic renderers later for the few highest-volume families that must always be correct, such as number lines, coordinate grids, basic circuits, lens rays, pulley/free-body diagrams, and common geometry figures.
