# trying-tikz

Tiny harness for testing how well OpenAI and Groq generate worksheet-style TikZ.

## Setup

Put keys in `.env`:

```text
OPENAI_API_KEY=...
GROQ_API_KEY=...
```

Run both providers on three built-in prompts:

```powershell
python try_tikz.py --provider both
```

Run the advanced math/science suite:

```powershell
python try_tikz.py --provider groq --suite advanced
```

Run the tougher worksheet stress suite:

```powershell
python try_tikz.py --provider groq --suite hardcore
```

Run one provider:

```powershell
python try_tikz.py --provider openai
python try_tikz.py --provider groq
```

If OpenAI billing is inactive, the script records the first account error and skips the remaining OpenAI prompts in that run.

Try your own worksheet figure prompt:

```powershell
python try_tikz.py --provider both --prompt 'Draw a circle with center $O$ and radius $10\text{ cm}$.'
```

PowerShell expands `$O` inside double quotes, so use single quotes for LaTeX-style math. For long prompts, put the text in a file and run:

```powershell
python try_tikz.py --provider both --prompt-file prompt.txt
```

Override models:

```powershell
python try_tikz.py --openai-model gpt-5.4-mini --groq-model llama-3.3-70b-versatile
```

Outputs go to `runs/<timestamp>/`:

- `.tikz` raw model output, cleaned when possible
- `.tex` standalone wrapper
- `summary.json` with model, latency, usage when returned, paths, and render status
- `score` inside `summary.json` with pass rate, token total, warnings, and failures

Collect the latest successful PDF for each prompt:

```powershell
python try_tikz.py --collect-best
```

## Rendering

The script tries `tectonic`, then `pdflatex`, then `lualatex`, then Codex's bundled Tectonic. If none are available, it still writes `.tikz` and `.tex` and records `"rendered": false`.

For local PDFs outside Codex, install Tectonic and rerun:

```powershell
winget install Tectonic.Tectonic
```

Groq GPT-OSS models use `reasoning_effort: low` to keep test runs cheaper.
If GPT-OSS trips Groq's `tool_use_failed` geometry behavior, the script retries once with `llama-3.1-8b-instant`.

The model prompt intentionally asks for simple TikZ only, explicit coordinates, centered layouts, short offset labels, and no overlapping labels/arrows. This is more reliable for worksheets than clever generated TikZ.
For worksheet production, keep fixed TikZ templates for common diagram families such as circuits, pulleys, waves, fractions, methane, and simple electrostatics. Use the model for open-ended diagrams, then render and visually review.
