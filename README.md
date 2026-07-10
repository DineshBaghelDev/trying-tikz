# trying-tikz

Tiny Python harness for testing worksheet-style TikZ generation with OpenAI and Groq.

The CLI is still `try_tikz.py`, but the code now lives under `tikz_harness/` so pipelines can be swapped without mixing experiments into one file.

## Layout

- `try_tikz.py` - thin compatibility CLI shim.
- `tikz_harness/core.py` - shared provider calls, rendering, scoring, prompt loading, suite runner, and review-sheet helpers.
- `tikz_harness/pipelines/plain.py` - direct prompt to TikZ.
- `tikz_harness/pipelines/template_guided.py` - first-pass drawing brief, template exemplar, then fresh TikZ.
- `tikz_harness/pipelines/vision.py` - blueprint/code/render/vision-critique loop.
- `tikz_harness/deterministic.py` - typed specifications, exact constructions, validation, hardness scoring, and TikZ rendering.
- `tikz_harness/pipelines/deterministic.py` - model-to-spec pipeline; models describe intent rather than drawing code.
- `tikz_harness/templates/library.py` - few-shot TikZ exemplars only; no locked/direct templates.
- `test_harness.py` - offline functional checks.

## Setup

Install the deterministic geometry engine:

```powershell
python -m pip install -r requirements.txt
```

Put keys in `.env`:

```text
OPENAI_API_KEY=...
GROQ_API_KEY=...
```

## Run

Interactive model, pipeline, and prompt picker:

```powershell
python test_diagrams.py
```

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

Run an external model matrix:

```powershell
copy model_matrix.example.json model_matrix.json
python try_tikz.py --provider none --model-config model_matrix.json --prompt-suite-file stress_prompts_90.json --pipeline templates --retries 1 --runs-dir runs\model-matrix
```

The model matrix uses OpenAI-compatible `/chat/completions` APIs. Add keys to `.env` as needed:

```text
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
XAI_API_KEY=...
SPARK_API_KEY=...
```

Pipeline choices:

- `--pipeline plain` - one model call, then compile/repair.
- `--pipeline templates` - expand the prompt into a drawing brief, inject the nearest exemplar, then compile/repair.
- `--pipeline vision` - JSON spatial blueprint, TikZ generation, and optional rendered-image critique.
- `--pipeline deterministic` - ask each model for typed JSON, compute derived geometry, validate constraints, and render TikZ in code.

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

The deterministic path is based on reusable primitives rather than prompt-specific templates. SymPy Geometry performs midpoint, intersection, perpendicular projection, angle-bisector and relationship calculations; TikZ handles vector output. The harness adds the typed interchange format, validation report, model comparison, grids, axes, cuboid projection, and rendering orchestration.

Each result records semantic validation and a domain-independent hardness breakdown in `summary.json`, so multiple models can be compared on the same specification task and renderer. Graphviz, Asymptote, and CircuiTikZ are not hard dependencies yet; add an adapter only when the regression suite exposes a diagram that the primitive layer cannot express.

Example:

```powershell
python try_tikz.py --provider groq --pipeline deterministic --prompt-suite-file diagram_regression_prompts.json --groq-models 'openai/gpt-oss-120b,qwen/qwen3-32b'
```

`--compare` runs deterministic alongside plain, templates, and vision.
