"""Typed, deterministic diagram construction and TikZ rendering.

Models describe intent as JSON. This module owns coordinates derived from geometric
relationships, validates those relationships, and emits the drawing code.
"""

import math

from sympy import simplify
from sympy.geometry import Line2D, Point2D, Segment2D, Triangle


SPEC_SYSTEM_PROMPT = r"""You translate worksheet diagram requests into deterministic JSON.
Return one JSON object only. Never return TikZ, markdown, or prose.

Schema:
{
  "domain": "geometry|plot|graph|physics|chemistry|circuit|general",
  "canvas": {"xmin": -5, "xmax": 5, "ymin": -4, "ymax": 4},
  "points": [
    {"id": "A", "at": [0, 0]},
    {"id": "M", "derive": "midpoint", "from": ["A", "B"]}
  ],
  "objects": [
    {"kind": "segment|line|arrow|polyline|polygon|circle|arc|point|label|axes|grid|cuboid|function", ...}
  ],
  "constraints": [
    {"kind": "perpendicular|parallel|collinear|equal_length|midpoint|angle_bisector", ...}
  ]
}

Point derivations:
- midpoint: {"id":"M","derive":"midpoint","from":["A","B"]}
- intersection: {"id":"X","derive":"intersection","from":["A","B","C","D"]}
- perpendicular_foot: {"id":"H","derive":"perpendicular_foot","from":["P","A","B"]}
- angle_bisector_point: {"id":"D","derive":"angle_bisector_point","from":["A","B","C"],"distance":3}
- offset: {"id":"Q","derive":"offset","from":["P"],"vector":[1,2]}

Object examples:
- {"kind":"segment","points":["A","B"],"style":"thick|dashed|dotted"}
- {"kind":"arrow","points":["A","B"],"label":"v"}
- {"kind":"polygon","points":["A","B","C"],"style":"thick"}
- {"kind":"circle","center":"O","radius":2}
- {"kind":"rectangle","at":[-1,-1],"width":2,"height":1}
- {"kind":"ellipse","center":"O","rx":2,"ry":1}
- {"kind":"arc","center":"O","radius":1,"start":0,"end":60}
- {"kind":"point","point":"A","label":"A","label_position":"above|below|left|right"}
- {"kind":"label","at":[0,-2],"text":"$x$"}
- {"kind":"axes","xrange":[-4,4],"yrange":[-3,3]}
- {"kind":"grid","xrange":[-4,4],"yrange":[-3,3],"step":1}
- {"kind":"function","expression":"x^2","xrange":[-2,2],"samples":41}
- {"kind":"cuboid","origin":[-2,-1],"width":3,"height":2,"depth":[1,0.7]}

Constraint examples:
- {"kind":"perpendicular","lines":[["A","B"],["C","D"]]}
- {"kind":"parallel","lines":[["A","B"],["C","D"]]}
- {"kind":"collinear","points":["A","B","C"]}
- {"kind":"equal_length","segments":[["A","B"],["C","D"]]}
- {"kind":"midpoint","point":"M","segment":["A","B"]}
- {"kind":"angle_bisector","ray":["B","D"],"angle":["A","B","C"]}

Use explicit base points and derived points for exact relationships. Include every important
mathematical relationship as a constraint. Keep labels short and objects within the canvas.
For unsupported specialist symbols, compose them from polygon, polyline, circle, arrow and label.
"""


def _v(a, b):
    return (b[0] - a[0], b[1] - a[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _scale(v, k):
    return (v[0] * k, v[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _length(v):
    return math.hypot(*v)


def _unit(v):
    n = _length(v)
    if n < 1e-12:
        raise ValueError("zero-length geometric direction")
    return (v[0] / n, v[1] / n)


def _fmt(value):
    value = float(value)
    value = 0.0 if abs(value) < 0.0005 else value
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _pt(value):
    return f"({_fmt(value[0])},{_fmt(value[1])})"


def _tex(text):
    return str(text).replace("\\", r"\textbackslash ").replace("{", r"\{").replace("}", r"\}")


def _math_text(text):
    text = str(text)
    return text if text.startswith("$") and text.endswith("$") else _tex(text)


def resolve_points(spec):
    points = {}
    pending = list(spec.get("points", []))
    for _ in range(len(pending) + 1):
        remaining = []
        for item in pending:
            try:
                points[item["id"]] = _resolve_point(item, points)
            except KeyError:
                remaining.append(item)
        if not remaining:
            return points
        if len(remaining) == len(pending):
            missing = ", ".join(str(item.get("id")) for item in remaining)
            raise ValueError(f"unresolved or cyclic points: {missing}")
        pending = remaining
    return points


def _resolve_point(item, points):
    if "at" in item:
        x, y = item["at"]
        return Point2D(x, y)
    kind = item.get("derive")
    refs = [points[name] for name in item.get("from", [])]
    if kind == "midpoint":
        return refs[0].midpoint(refs[1])
    if kind == "offset":
        dx, dy = item["vector"]
        return refs[0] + Point2D(dx, dy)
    if kind == "intersection":
        a, b, c, d = refs
        intersections = Line2D(a, b).intersection(Line2D(c, d))
        if not intersections or not isinstance(intersections[0], Point2D):
            raise ValueError("lines do not have one unique intersection")
        return intersections[0]
    if kind == "perpendicular_foot":
        p, a, b = refs
        return Line2D(a, b).projection(p)
    if kind == "angle_bisector_point":
        a, vertex, c = refs
        bisector = Triangle(a, vertex, c).bisectors()[vertex]
        direction = _unit(_v(vertex, bisector.p2))
        dx, dy = _scale(direction, float(item.get("distance", 3)))
        return vertex + Point2D(dx, dy)
    raise ValueError(f"unknown point derivation: {kind}")


def validate_spec(spec, tolerance=1e-6):
    errors = []
    try:
        points = resolve_points(spec)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {"valid": False, "errors": [str(exc)], "checks": 0, "passed": 0}
    constraints = spec.get("constraints", [])
    passed = 0
    for index, constraint in enumerate(constraints):
        try:
            ok = _check_constraint(constraint, points, tolerance)
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
            errors.append(f"constraint {index}: {exc}")
            continue
        if ok:
            passed += 1
        else:
            errors.append(f"constraint {index} failed: {constraint.get('kind')}")
    return {"valid": not errors, "errors": errors, "checks": len(constraints), "passed": passed}


def _lines(constraint, points):
    return [Line2D(points[a], points[b]) for a, b in constraint["lines"]]


def _check_constraint(c, p, tolerance):
    kind = c["kind"]
    if kind == "perpendicular":
        a, b = _lines(c, p)
        return bool(a.is_perpendicular(b))
    if kind == "parallel":
        a, b = _lines(c, p)
        return bool(a.is_parallel(b))
    if kind == "collinear":
        return bool(Point2D.is_collinear(*(p[x] for x in c["points"])))
    if kind == "equal_length":
        lengths = [Segment2D(p[a], p[b]).length for a, b in c["segments"]]
        return all(simplify(length - lengths[0]) == 0 for length in lengths[1:])
    if kind == "midpoint":
        a, b = [p[x] for x in c["segment"]]
        return p[c["point"]].equals(a.midpoint(b))
    if kind == "angle_bisector":
        vertex, d = [p[x] for x in c["ray"]]
        a, angle_vertex, z = [p[x] for x in c["angle"]]
        if vertex != angle_vertex:
            return False
        bisector = Triangle(a, vertex, z).bisectors()[vertex]
        return bool(Line2D(vertex, d).is_parallel(Line2D(bisector.p1, bisector.p2)))
    raise ValueError(f"unknown constraint: {kind}")


def hardness(spec):
    objects = spec.get("objects", [])
    points = spec.get("points", [])
    constraints = spec.get("constraints", [])
    derived = sum("derive" in point for point in points)
    kinds = len({obj.get("kind") for obj in objects})
    raw = len(objects) + len(points) + 2 * len(constraints) + 2 * derived + kinds
    level = "easy" if raw < 12 else "medium" if raw < 25 else "hard" if raw < 45 else "extreme"
    return {"score": raw, "level": level, "objects": len(objects), "points": len(points),
            "constraints": len(constraints), "derived_points": derived, "primitive_kinds": kinds}


def render(spec):
    validation = validate_spec(spec)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    points = resolve_points(spec)
    lines = [r"\begin{tikzpicture}[>=Stealth]"]
    for obj in spec.get("objects", []):
        lines.extend(_render_object(obj, points))
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines), validation, hardness(spec)


def _render_object(obj, points):
    kind = obj["kind"]
    allowed_styles = {"", "thick", "dashed", "dotted", "gray", "thin", "very thick"}
    style = obj.get("style", "")
    if style not in allowed_styles:
        raise ValueError(f"unsupported style: {style}")
    option = f"[{style}]" if style else ""
    refs = [points[name] for name in obj.get("points", [])]
    if kind in ("segment", "line", "arrow"):
        arrow = "->" if kind == "arrow" else style
        option = f"[{arrow}]" if arrow else ""
        out = [f"\\draw{option} {_pt(refs[0])} -- {_pt(refs[1])};"]
        if obj.get("label"):
            mid = _scale(_add(refs[0], refs[1]), 0.5)
            out.append(f"\\node[above] at {_pt(mid)} {{{_math_text(obj['label'])}}};")
        return out
    if kind in ("polyline", "polygon"):
        path = " -- ".join(_pt(point) for point in refs)
        return [f"\\draw{option} {path}{' -- cycle' if kind == 'polygon' else ''};"]
    if kind == "circle":
        return [f"\\draw{option} {_pt(points[obj['center']])} circle ({_fmt(float(obj['radius']))});"]
    if kind == "rectangle":
        x, y = map(float, obj["at"])
        other = (x + float(obj["width"]), y + float(obj["height"]))
        return [f"\\draw{option} {_pt((x, y))} rectangle {_pt(other)};"]
    if kind == "ellipse":
        return [f"\\draw{option} {_pt(points[obj['center']])} ellipse ({_fmt(float(obj['rx']))} and {_fmt(float(obj['ry']))});"]
    if kind == "arc":
        center = points[obj["center"]]
        radius = float(obj["radius"])
        start = float(obj["start"])
        start_point = _add(center, (radius * math.cos(math.radians(start)), radius * math.sin(math.radians(start))))
        return [f"\\draw{option} {_pt(start_point)} arc ({_fmt(start)}:{_fmt(float(obj['end']))}:{_fmt(radius)}); "]
    if kind == "point":
        point = points[obj["point"]]
        out = [f"\\fill {_pt(point)} circle (1.5pt);"]
        if obj.get("label"):
            out.append(f"\\node[{obj.get('label_position', 'above')}] at {_pt(point)} {{{_math_text(obj['label'])}}};")
        return out
    if kind == "label":
        at = points[obj["point"]] if obj.get("point") else tuple(obj["at"])
        return [f"\\node[{obj.get('position', '')}] at {_pt(at)} {{{_math_text(obj['text'])}}};"]
    if kind == "grid":
        xmin, xmax = obj["xrange"]
        ymin, ymax = obj["yrange"]
        return [f"\\draw[step={_fmt(float(obj.get('step', 1)))},gray!35] ({xmin},{ymin}) grid ({xmax},{ymax});"]
    if kind == "axes":
        xmin, xmax = obj["xrange"]
        ymin, ymax = obj["yrange"]
        return [f"\\draw[->] ({xmin},0) -- ({xmax},0) node[right] {{$x$}};",
                f"\\draw[->] (0,{ymin}) -- (0,{ymax}) node[above] {{$y$}};"]
    if kind == "cuboid":
        x, y = map(float, obj.get("origin", [0, 0]))
        w, h = float(obj["width"]), float(obj["height"])
        dx, dy = map(float, obj.get("depth", [1, 0.7]))
        a, b, c, d = (x, y), (x+w, y), (x+w, y+h), (x, y+h)
        e, f, g, q = (_add(v, (dx, dy)) for v in (a, b, c, d))
        return [f"\\draw[thick] {_pt(a)} -- {_pt(b)} -- {_pt(c)} -- {_pt(d)} -- cycle;",
                f"\\draw[thick] {_pt(b)} -- {_pt(f)} -- {_pt(g)} -- {_pt(c)};",
                f"\\draw[thick] {_pt(d)} -- {_pt(q)} -- {_pt(g)};",
                f"\\draw[dashed] {_pt(a)} -- {_pt(e)} -- {_pt(f)};",
                f"\\draw[dashed] {_pt(e)} -- {_pt(q)};"]
    if kind == "function":
        samples = max(2, min(201, int(obj.get("samples", 41))))
        xmin, xmax = map(float, obj["xrange"])
        expression = obj["expression"]
        try:
            from sympy import lambdify, symbols, sympify
            x = symbols("x")
            fn = lambdify(x, sympify(expression), "math")
        except ImportError as exc:
            raise ValueError("function objects require SymPy") from exc
        coords = []
        for i in range(samples):
            value = xmin + (xmax - xmin) * i / (samples - 1)
            result = float(fn(value))
            if math.isfinite(result):
                coords.append(_pt((value, result)))
        return [f"\\draw{option} " + " -- ".join(coords) + ";"]
    raise ValueError(f"unknown object kind: {kind}")


def quality_metrics(spec):
    validation = validate_spec(spec)
    hard = hardness(spec)
    checks = validation["checks"]
    semantic = validation["passed"] / checks if checks else None
    return {"semantic_score": round(10 * semantic, 3) if semantic is not None else None,
            "constraint_coverage": checks, "validation": validation, "hardness": hard,
            "engine": "sympy-geometry+tikz", "domain": spec.get("domain", "general")}
