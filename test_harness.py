"""Offline functional tests for the try_tikz harness.

Covers the pure-Python logic added for the three-pipeline comparison: JSON parsing,
blueprint linting, scoring, candidate selection, model fan-out, template retrieval, and
prompt assembly. No network or LaTeX calls, so it is fast and safe to run any time.

Run:  python test_harness.py
"""

import try_tikz as t
from tikz_harness import deterministic as det
from tikz_harness.pipelines import deterministic as adaptive
from tikz_harness.templates import library as templates_mod

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")


# ---- parse_json_loose ----------------------------------------------------------------
def test_parse_json_loose():
    print("parse_json_loose")
    check("plain object", t.parse_json_loose('{"a": 1}') == {"a": 1})
    check("fenced json", t.parse_json_loose("```json\n{\"a\": 2}\n```") == {"a": 2})
    check("prose around", t.parse_json_loose('here:\n{"a": 3}\nthanks') == {"a": 3})


# ---- lint_blueprint ------------------------------------------------------------------
def test_lint_blueprint():
    print("lint_blueprint")
    clean = {
        "canvas": {"xmin": -5, "xmax": 5, "ymin": -4, "ymax": 4},
        "objects": [
            {"id": "a", "type": "point", "coords": [[0, 0]]},
            {"id": "b", "type": "point", "coords": [[2, 1]]},
        ],
        "labels": [
            {"text": "A", "anchor_id": "a", "direction": "above", "offset": 0.4},
            {"text": "B", "anchor_id": "b", "direction": "below", "offset": 0.4},
        ],
    }
    check("clean has no warnings", t.lint_blueprint(clean) == [])

    dirty = {
        "canvas": {"xmin": -5, "xmax": 5, "ymin": -4, "ymax": 4},
        "objects": [
            {"id": "a", "type": "point", "coords": [[0, 0]]},
            {"id": "b", "type": "point", "coords": [[0, 0]]},   # shares coords with a
            {"id": "c", "type": "point", "coords": [[99, 99]]}, # out of bounds
        ],
        "labels": [
            {"text": "X", "anchor_id": "a", "direction": "above", "offset": 0.3},
            {"text": "Y", "anchor_id": "a", "direction": "above", "offset": 0.3},  # overlap
            {"text": "Z", "anchor_id": "missing", "direction": "left"},            # bad anchor
        ],
    }
    w = t.lint_blueprint(dirty)
    check("detects out_of_bounds", "object_out_of_bounds" in w)
    check("detects shared coords", "objects_share_coords" in w)
    check("detects missing anchor", "label_anchor_missing" in w)
    check("detects label overlap", "label_overlap" in w)


# ---- score ---------------------------------------------------------------------------
def test_score():
    print("score")
    check("failed render = -100", t.score({"rendered": False}) == -100)
    check("rendered no vision = 6.0", t.score({"rendered": True, "warnings": [], "blueprint_warnings": []}) == 6.0)
    check("vision score used", t.score({"rendered": True, "warnings": [], "blueprint_warnings": [], "vision": {"score": 9}}) == 9.0)
    check("warnings subtract", t.score({"rendered": True, "warnings": ["x", "y"], "blueprint_warnings": ["z"]}) == 6.0 - 1.5)
    check("visual score caps exact score", t.score({"rendered": True, "warnings": [], "blueprint_warnings": [],
          "deterministic": {"semantic_score": 10}, "vision": {"score": 5}}) == 5.0)


# ---- best_results --------------------------------------------------------------------
def test_best_results():
    print("best_results")
    results = [
        {"provider": "groq", "model": "m1", "prompt_name": "p", "rendered": True, "score": 5},
        {"provider": "groq", "model": "m1", "prompt_name": "p", "rendered": True, "score": 8},
        {"provider": "groq", "model": "m2", "prompt_name": "p", "rendered": True, "score": 6},
    ]
    by_prompt = t.best_results(results)
    check("collapses to 1 per prompt", len(by_prompt) == 1)
    check("keeps max score", list(by_prompt.values())[0]["score"] == 8)
    by_model = t.best_results(results, by_model=True)
    check("keeps per-model", len(by_model) == 2)
    check("m1 best is 8", by_model[("groq", "p", "m1")]["score"] == 8)


# ---- _model_pairs --------------------------------------------------------------------
def test_model_pairs():
    print("_model_pairs")

    class A:
        provider = "groq"; openai_model = "o"; groq_models = "a,b,c"
    check("groq fans out to 3", len(t._model_pairs(A)) == 3)

    class B:
        provider = "both"; openai_model = "o"; groq_models = "a,b"
    pairs = t._model_pairs(B)
    check("both = openai + 2 groq", pairs == [("openai", "o"), ("groq", "a"), ("groq", "b")])

    class C:
        provider = "openai"; openai_model = "o"; groq_models = "a,b"
    check("openai only", t._model_pairs(C) == [("openai", "o")])

    class D:
        provider = "groq"; openai_model = "o"; groq_models = "qwen3-32b,gpt-oss-20b"
    check("Groq shorthand normalized", t._model_pairs(D) == [
        ("groq", "qwen/qwen3-32b"), ("groq", "openai/gpt-oss-20b")])


# ---- retrieve_template + templates_prompt --------------------------------------------
def test_retrieval():
    print("retrieve_template (uses embeddings if server up, else jaccard)")
    cases = {
        "Draw a block on an inclined ramp with friction and normal force": "physics-inclined-plane",
        "Draw benzene aromatic ring, not cyclohexane": "chem-benzene-aromatic",
        "Draw a two-stage probability tree of outcomes": "math-probability-tree",
        "Draw a cuboid in 3D with a space diagonal": "math-3d-cuboid",
    }
    for prompt, expected in cases.items():
        r = t.retrieve_template(prompt)
        check(f"{expected} <- {prompt[:32]!r} ({r[2] if r else 'none'})", bool(r) and r[0] == expected)

    tmpl = templates_mod.TEMPLATES["chem-benzene-aromatic"]
    p = t.templates_prompt("Draw benzene", "Draw a regular aromatic hexagon with C6H6 below.", tmpl)
    check("exemplar embeds tikz", tmpl["tikz"][:20] in p)
    check("exemplar keeps request", "Original request:" in p and "Draw benzene" in p)
    check("expanded brief included", "Expanded drawing brief:" in p and "aromatic hexagon" in p)


# ---- clean_tikz / fix_unsafe_macros / slug -------------------------------------------
def test_text_utils():
    print("text utils")
    raw = "```latex\n\\begin{tikzpicture}\n\\draw (0,0)--(1,1);\n\\end{tikzpicture}\n```"
    cleaned = t.clean_tikz(raw)
    check("strips fences", cleaned.startswith("\\begin{tikzpicture}") and cleaned.endswith("\\end{tikzpicture}"))
    check("fix_unsafe \\( -> $", "$x$" in t.fix_unsafe_macros(r"\(x\)"))
    check("fixes node ++ offset", "\\node at ($(c)+(30:0.7)$)" in t.fix_unsafe_macros(r"\node at (c) ++(30:0.7) {$\theta$};"))
    check("slug", t.slug("Physics: Inclined Plane!") == "physics-inclined-plane")
    blank_stats = t.source_stats("\\begin{tikzpicture}\n\\end{tikzpicture}")
    check("empty tikz rejected", t.source_error("\\begin{tikzpicture}\n\\end{tikzpicture}", blank_stats) == "Model returned an empty tikzpicture")
    bad_stats = t.source_stats("\\begin{tikzpicture}\n\\coordinate (H) at (intersection of A--B and C--D);\n\\end{tikzpicture}")
    check("intersection syntax rejected", t.source_error("\\begin{tikzpicture}\n\\coordinate (H) at (intersection of A--B and C--D);\n\\end{tikzpicture}", bad_stats) == "Unsupported intersection syntax; use explicit coordinates or named paths with name intersections")
    macro_tikz = "\\begin{tikzpicture}\n\\def\\dx{0.5}\n\\draw (0,0)--(1,1);\n\\end{tikzpicture}"
    check("unsafe macro rejected", "Unsupported \\def" in t.source_error(macro_tikz, t.source_stats(macro_tikz)))
    draw_stats = t.source_stats("\\begin{tikzpicture}\n\\draw (0,0)--(1,1);\n\\end{tikzpicture}")
    check("real tikz accepted", t.source_error("\\begin{tikzpicture}\n\\draw (0,0)--(1,1);\n\\end{tikzpicture}", draw_stats) is None)


# ---- templates.py integrity ----------------------------------------------------------
def test_templates_integrity():
    print("templates integrity")
    check("21 templates", len(templates_mod.TEMPLATES) == 21)
    ok = True
    for name, tm in templates_mod.TEMPLATES.items():
        if not tm.get("description") or "tikzpicture" not in tm.get("tikz", ""):
            ok = False
            print(f"    bad template: {name}")
    check("all have description + tikzpicture", ok)
    check("no locked templates", not any(tm.get("locked") for tm in templates_mod.TEMPLATES.values()))


# ---- deterministic specification engine ---------------------------------------------
def test_deterministic():
    print("deterministic")
    spec = {
        "domain": "geometry",
        "points": [
            {"id": "A", "at": [-3, 0]}, {"id": "B", "at": [0, 0]},
            {"id": "C", "at": [2, 2]},
            {"id": "D", "derive": "angle_bisector_point", "from": ["A", "B", "C"]},
            {"id": "P", "at": [1, 3]},
            {"id": "H", "derive": "perpendicular_foot", "from": ["P", "A", "C"]},
        ],
        "objects": [
            {"kind": "segment", "points": ["B", "A"]},
            {"kind": "segment", "points": ["B", "C"]},
            {"kind": "segment", "points": ["B", "D"], "style": "dashed"},
            {"kind": "segment", "points": ["P", "H"]},
            {"kind": "cuboid", "origin": [-2, -1], "width": 2, "height": 1.5, "depth": [0.8, 0.5]},
        ],
        "constraints": [
            {"kind": "angle_bisector", "ray": ["B", "D"], "angle": ["A", "B", "C"]},
            {"kind": "perpendicular", "lines": [["P", "H"], ["A", "C"]]},
        ],
    }
    tikz, validation, hard = det.render(spec)
    check("derived constraints pass", validation["valid"] and validation["passed"] == 2)
    check("generic objects render", "dashed" in tikz and tikz.count("\\draw[thick]") >= 3)
    check("hardness is reported", hard["score"] > 0 and hard["level"] in {"easy", "medium", "hard", "extreme"})
    check("semantic score is exact", det.quality_metrics(spec)["semantic_score"] == 10.0)
    check("empty constraints are unscored", det.quality_metrics({"points": [], "objects": []})["semantic_score"] is None)

    bad = {"points": [{"id": "A", "at": [0, 0]}, {"id": "B", "at": [1, 0]},
                      {"id": "C", "at": [0, 1]}, {"id": "D", "at": [1, 1]}],
           "objects": [], "constraints": [{"kind": "perpendicular", "lines": [["A", "B"], ["C", "D"]]}]}
    check("false relation rejected", not det.validate_spec(bad)["valid"])
    check("canonical physics uses trusted template",
          adaptive.choose_route("physics-incline", "Draw a block on an inclined plane")[0] == "trusted-template")
    check("specialist diagram uses adaptive fallback",
          adaptive.choose_route("chem-special", "Draw an unusual reaction apparatus")[0] in {"template", "vision"})


if __name__ == "__main__":
    for fn in [test_parse_json_loose, test_lint_blueprint, test_score, test_best_results,
               test_model_pairs, test_retrieval, test_text_utils, test_templates_integrity,
               test_deterministic]:
        fn()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
