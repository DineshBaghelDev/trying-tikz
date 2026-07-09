"""Reusable TikZ exemplar templates for worksheet figures.

Each entry has a plain-English ``description`` (this is what gets embedded for semantic
retrieval -- never the raw TikZ) and a ``tikz`` body that compiles with the standard
preamble in ``try_tikz.wrap_tex`` (arrows.meta, calc, decorations, patterns, positioning,
quotes). Templates are used as few-shot exemplars: the model sees a nearby example for
structure/style and generates a fresh figure for the actual request.

The first seven are restored from commit f48ad0b; the rest were added for families the
model-first generator struggles with (inclined planes, ray optics, aromatic rings,
titration curves, probability trees, 3D solids, electrochemical cells).
"""

TEMPLATES = {
    "circuit": {
        "description": "electric circuit loop with a battery, a switch, two resistors, an ammeter and a voltmeter",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw (-4,2) -- (4,2) -- (4,-2) -- (-4,-2);
\draw (-4,-2) -- (-4,-0.6) (-4,0.6) -- (-4,2);
\draw (-4.35,0.6) -- (-3.65,0.6);
\draw (-4.2,-0.6) -- (-3.8,-0.6);
\node[left] at (-4.4,0) {Battery};
\draw (-1.3,2) -- (-0.8,2.35) -- (-0.3,2);
\node[above] at (-0.8,2.35) {Switch};
\draw (-1,-2) circle (0.35) node {$A$};
\draw (2,2) -- (2,-2);
\draw (2,1.25) rectangle (3.1,1.65) node[midway] {$R_1$};
\draw (2,-0.85) rectangle (3.1,-0.45) node[midway] {$R_2$};
\draw (3.1,1.45) -- (4,1.45);
\draw (3.1,-0.65) -- (4,-0.65);
\draw (4.75,-0.65) circle (0.35) node {$V$};
\draw (4,-0.45) -- (4.5,-0.45);
\draw (4,-0.85) -- (4.5,-0.85);
\end{tikzpicture}""",
    },
    "pulley-system": {
        "description": "two-block pulley system on a table with a hanging mass and force arrows for tension, normal, weight and friction",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw (-4,0) -- (1.4,0);
\draw (-2.5,0) rectangle (-1.2,0.8) node[midway] {$m_1$};
\draw (1.6,1.05) circle (0.35);
\draw (-1.2,0.8) -- (1.6,1.4) -- (2.75,0.1) -- (2.75,-0.75);
\draw (2.35,-1.65) rectangle (3.15,-0.75) node[midway] {$m_2$};
\draw[->] (-1.85,0.8) -- (-1.85,1.55) node[above] {$N$};
\draw[->] (-1.85,0) -- (-1.85,-0.8) node[below] {$m_1g$};
\draw[->] (-1.2,0.55) -- (-0.35,0.55) node[above] {$T$};
\draw[->] (-2.5,0.55) -- (-3.25,0.55) node[above] {$f$};
\draw[->] (3.15,-1.2) -- (3.85,-1.2) node[right] {$a$};
\draw[->] (2.75,-1.65) -- (2.75,-2.45) node[below] {$m_2g$};
\draw[->] (2.35,-1.2) -- (1.7,-1.2) node[left] {$T$};
\end{tikzpicture}""",
    },
    "physics-spring-mass": {
        "description": "horizontal spring attached to a block on a floor with wall, displacement axis, equilibrium line and restoring force",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[thick] (-4,-1) -- (4,-1);
\draw[thick] (-3.6,-1) -- (-3.6,1.3);
\draw (-3.6,0.25) -- (-3.1,0.25) -- (-2.9,0.55) -- (-2.5,-0.05)
  -- (-2.1,0.55) -- (-1.7,-0.05) -- (-1.3,0.55) -- (-0.9,0.25);
\draw[fill=gray!15] (-0.9,-0.35) rectangle (0.5,0.85);
\node at (-0.2,0.25) {$m$};
\draw[dashed] (1.0,-1.0) -- (1.0,1.1);
\node[below] at (1.0,-1.0) {$x=0$};
\draw[->] (0.5,0.25) -- (-0.5,0.25) node[above] {$F=-kx$};
\draw[->] (-3.8,-1.35) -- (3.6,-1.35) node[right] {$x$};
\end{tikzpicture}""",
    },
    "physics-simple-pendulum": {
        "description": "simple pendulum with pivot, string length, angle from vertical, bob, tension, weight and tangential component",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\coordinate (P) at (0,2.6);
\coordinate (B) at (1.4,-1.2);
\fill (P) circle (2pt) node[above] {pivot};
\draw[dashed] (P) -- (0,-1.6);
\draw[thick] (P) -- (B) node[midway,right] {$L$};
\draw[fill=gray!15] (B) circle (0.22) node[right=0.25] {$m$};
\draw (0,1.6) arc (-90:-62:1.0);
\node at (0.38,1.45) {$\theta$};
\draw[->,thick] (B) -- ++(117:1.0) node[above] {$T$};
\draw[->,thick] (B) -- ++(0,-1.1) node[below] {$mg$};
\draw[->] (B) -- ++(28:1.0) node[right] {$mg\sin\theta$};
\draw[dashed] (0.7,-1.45) arc (-128:-52:0.95);
\end{tikzpicture}""",
    },
    "waves": {
        "description": "transverse sine wave on axes showing amplitude, wavelength, crest, trough and the equilibrium line",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[->] (-4,0) -- (4.3,0) node[right] {$x$};
\draw[->] (0,-1.6) -- (0,1.8) node[above] {$y$};
\draw[thick, domain=-3.7:3.7, samples=80] plot (\x,{sin(120*\x)});
\draw[dashed] (-4,1) -- (4,1);
\draw[dashed] (-4,-1) -- (4,-1);
\draw[<->] (0.45,0) -- (0.45,1) node[midway,right] {$A$};
\draw[<->] (-2.25,-1.35) -- (0.75,-1.35) node[midway,below] {$\lambda$};
\node[above] at (-2.25,1) {crest};
\node[below] at (2.25,-1) {trough};
\node[below right] at (0.7,0) {equilibrium};
\end{tikzpicture}""",
    },
    "fraction": {
        "description": "number line from 0 to 1 divided into equal parts with one fraction emphasized by an arrow",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[->] (-0.2,0) -- (8.7,0);
\draw[line width=2pt] (0,0) -- (3,0);
\foreach \x in {0,1,...,8} \draw (\x,-0.12) -- (\x,0.12);
\node[below] at (0,-0.12) {$0$};
\node[below] at (8,-0.12) {$1$};
\node[above] at (3,0.65) {$\frac{3}{8}$};
\draw[->, thick] (3,0.5) -- (3,0.16);
\end{tikzpicture}""",
    },
    "chem-methane": {
        "description": "methane molecule with a central carbon bonded to four hydrogens and a labelled bond angle",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\node[circle,draw,inner sep=2pt] (C) at (0,0) {$C$};
\node (H1) at (0,1.5) {$H$};
\node (H2) at (-1.35,-0.8) {$H$};
\node (H3) at (1.35,-0.8) {$H$};
\node (H4) at (1.55,0.35) {$H$};
\draw (C) -- (H1);
\draw (C) -- (H2);
\draw (C) -- (H3);
\draw[dashed] (C) -- (H4);
\draw (0.35,-0.2) arc (-30:75:0.45);
\node at (0.95,0.55) {$109.5^\circ$};
\end{tikzpicture}""",
    },
    "electrostatics": {
        "description": "electric dipole with a positive and a negative charge, curved field lines, separation distance and force on a test charge",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\node[circle,draw,inner sep=2pt] (P) at (-2,0) {$+q$};
\node[circle,draw,inner sep=2pt] (N) at (2,0) {$-q$};
\draw[->,gray] (-1.65,0.35) .. controls (-0.6,1.0) and (0.6,1.0) .. (1.65,0.35);
\draw[->,gray] (-1.65,0) -- (1.65,0);
\draw[->,gray] (-1.65,-0.35) .. controls (-0.6,-1.0) and (0.6,-1.0) .. (1.65,-0.35);
\draw[<->] (-2,-1.4) -- (2,-1.4) node[midway,below] {$r$};
\node[circle,draw,inner sep=1.5pt] (Q) at (0,2) {$q_0$};
\draw[->,thick] (Q) -- (-0.8,1.2) node[left] {$F$};
\end{tikzpicture}""",
    },
    "math-law-of-sines": {
        "description": "triangle inscribed in a circle with labelled sides and vertices for the law of sines",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\coordinate (A) at (0,0);
\coordinate (B) at (4,0);
\coordinate (C) at (1.4,2.8);
\draw (2,0.85) circle (2.17);
\draw[thick] (A) -- (B) -- (C) -- cycle;
\node[below left] at (A) {$A$};
\node[below right] at (B) {$B$};
\node[above] at (C) {$C$};
\node[below] at (2,0) {$c$};
\node[left] at (0.7,1.4) {$b$};
\node[right] at (2.7,1.4) {$a$};
\draw[dashed] (C) -- (2.6,-1.1);
\node at (2,-1.6) {$\frac{a}{\sin A}=\frac{b}{\sin B}=\frac{c}{\sin C}$};
\end{tikzpicture}""",
    },
    "math-coordinate-plane": {
        "description": "coordinate plane with grid, axes, two labelled points and a segment between them",
        "tikz": r"""\begin{tikzpicture}[scale=0.65]
\draw[gray!25] (-5,-4) grid (5,5);
\draw[->] (-5.3,0) -- (5.4,0) node[right] {$x$};
\draw[->] (0,-4.3) -- (0,5.3) node[above] {$y$};
\foreach \x in {-5,-4,...,5} \draw (\x,0.08) -- (\x,-0.08) node[below,scale=0.7] {$\x$};
\foreach \y in {-4,-3,...,5} \draw (0.08,\y) -- (-0.08,\y) node[left,scale=0.7] {$\y$};
\fill (-2,1) circle (2pt) node[above left] {$A(-2,1)$};
\fill (3,4) circle (2pt) node[above right] {$B(3,4)$};
\draw[thick] (-2,1) -- (3,4);
\end{tikzpicture}""",
    },
    "math-triangle-side-angle": {
        "description": "triangle ABC with side length labels and a small marked angle at vertex A",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\coordinate (A) at (0,0);
\coordinate (B) at (4.4,0);
\coordinate (C) at (1.25,3.0);
\draw[thick] (A) -- (B) -- (C) -- cycle;
\node[below left] at (A) {$A$};
\node[below right] at (B) {$B$};
\node[above] at (C) {$C$};
\node[below] at (2.2,0) {$5\text{ cm}$};
\node[right] at (2.85,1.5) {$6\text{ cm}$};
\node[left] at (0.6,1.5) {$7\text{ cm}$};
\draw (0.55,0) arc (0:67:0.55);
\node at (0.75,0.28) {$\theta$};
\end{tikzpicture}""",
    },
    "physics-inclined-plane": {
        "description": "block resting on an inclined ramp with weight, normal and friction force arrows and the incline angle theta",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[thick] (-4,-1.5) -- (3,-1.5) -- (3,1) -- cycle;
\draw (1.6,-1.5) arc (180:159:1.4);
\node at (1,-1.2) {$\theta$};
\begin{scope}[shift={(-0.1,-0.02)},rotate=20]
\draw[fill=gray!15] (-0.55,0) rectangle (0.55,0.75);
\node at (0,0.37) {$m$};
\end{scope}
\coordinate (c) at (-0.1,0.35);
\draw[->,thick] (c) -- ++(0,-1.7) node[below] {$mg$};
\draw[->,thick] (c) -- ++(200:1.4) node[below left] {$f$};
\draw[->,thick] (c) -- ++(110:1.5) node[above left] {$N$};
\end{tikzpicture}""",
    },
    "math-vector-components": {
        "description": "vector from the origin with horizontal and vertical components, dashed projection lines and angle theta",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[->] (-0.2,0) -- (4.5,0) node[right] {$x$};
\draw[->] (0,-0.2) -- (0,3.2) node[above] {$y$};
\draw[->,thick] (0,0) -- (3.6,2.4) node[above right] {$\vec v$};
\draw[dashed] (3.6,0) -- (3.6,2.4);
\draw[dashed] (0,2.4) -- (3.6,2.4);
\draw[->] (0,0) -- (3.6,0) node[midway,below] {$v_x$};
\draw[->] (3.6,0) -- (3.6,2.4) node[midway,right] {$v_y$};
\draw (0.8,0) arc (0:34:0.8);
\node at (1.05,0.35) {$\theta$};
\end{tikzpicture}""",
    },
    "physics-convex-lens": {
        "description": "convex lens ray diagram with a principal axis, focal points, an upright object arrow and an inverted real image",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[->] (-5.2,0) -- (5.2,0) node[right] {axis};
\draw[very thick,<->] (0,-2) -- (0,2);
\filldraw (-2,0) circle (1.2pt) node[below right] {$F$};
\filldraw (2,0) circle (1.2pt) node[below left] {$F$};
\filldraw (-4,0) circle (1.2pt) node[below] {$2F$};
\filldraw (4,0) circle (1.2pt) node[below] {$2F$};
\draw[->,very thick] (-4,0) -- (-4,1.2) node[above] {object};
\draw (-4,1.2) -- (0,1.2) -- (4,-1.2);
\draw (-4,1.2) -- (4,-1.2);
\draw[->,very thick] (4,0) -- (4,-1.2) node[below right] {image};
\end{tikzpicture}""",
    },
    "chem-benzene-aromatic": {
        "description": "benzene aromatic ring drawn as a regular hexagon with an inner circle, clearly not cyclohexane",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\foreach \a in {0,60,120,180,240,300} \coordinate (v\a) at (\a:1.7);
\draw[thick] (v0) -- (v60) -- (v120) -- (v180) -- (v240) -- (v300) -- cycle;
\draw (0,0) circle (1.05);
\node[below] at (0,-2.2) {$C_6H_6$};
\end{tikzpicture}""",
    },
    "chem-titration-curve": {
        "description": "titration curve of pH versus added volume with a buffer region and an equivalence point above pH 7",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[->] (0,0) -- (7,0) node[right] {Volume};
\draw[->] (0,0) -- (0,6) node[above] {pH};
\draw[thick] (0.3,1.1) .. controls (2,2.1) and (2.6,2.6) .. (3.1,3.0)
  .. controls (3.4,3.4) and (3.5,4.9) .. (3.7,5.2)
  .. controls (4.6,5.6) and (5.6,5.7) .. (6.5,5.8);
\draw[dashed] (3.6,0) -- (3.6,5.05) -- (0,5.05);
\filldraw (3.6,5.05) circle (1.6pt);
\node[right] at (3.7,5.05) {equivalence};
\node[below] at (1.7,1.0) {buffer};
\end{tikzpicture}""",
    },
    "math-probability-tree": {
        "description": "two-stage probability tree with branches labelled by probabilities and outcome labels at the leaves",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\coordinate (s) at (-4,0);
\coordinate (r) at (-1,1.8);
\coordinate (nr) at (-1,-1.8);
\draw (s) -- (r) node[midway,above] {$0.3$};
\draw (s) -- (nr) node[midway,below] {$0.7$};
\draw (r) -- (2,2.8) node[midway,above] {$0.4$};
\draw (r) -- (2,0.9) node[midway,below] {$0.6$};
\draw (nr) -- (2,-0.9) node[midway,above] {$0.4$};
\draw (nr) -- (2,-2.8) node[midway,below] {$0.6$};
\node[left] at (s) {Start};
\node[right] at (2,2.8) {Late};
\node[right] at (2,0.9) {On time};
\node[right] at (2,-0.9) {Late};
\node[right] at (2,-2.8) {On time};
\end{tikzpicture}""",
    },
    "math-3d-cuboid": {
        "description": "three dimensional rectangular cuboid in oblique projection with labelled vertices, hidden dashed edges and a space diagonal",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\coordinate (A) at (0,0);
\coordinate (B) at (3,0);
\coordinate (C) at (3,2);
\coordinate (D) at (0,2);
\coordinate (E) at (1,0.7);
\coordinate (F) at (4,0.7);
\coordinate (G) at (4,2.7);
\coordinate (H) at (1,2.7);
\draw (A) -- (B) -- (C) -- (D) -- cycle;
\draw (F) -- (G) -- (H);
\draw (B) -- (F);
\draw (C) -- (G);
\draw (D) -- (H);
\draw[dashed] (A) -- (E);
\draw[dashed] (E) -- (F);
\draw[dashed] (E) -- (H);
\draw[thick] (A) -- (G);
\node[below left] at (A) {$A$};
\node[below right] at (B) {$B$};
\node[right] at (C) {$C$};
\node[left] at (D) {$D$};
\node[below left] at (E) {$E$};
\node[right] at (F) {$F$};
\node[above right] at (G) {$G$};
\node[above] at (H) {$H$};
\end{tikzpicture}""",
    },
    "chem-galvanic-cell": {
        "description": "galvanic Daniell cell with zinc and copper electrodes in two beakers, a salt bridge, a voltmeter and electron flow",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw (-3.3,-1.6) rectangle (-1.1,1);
\draw (1.1,-1.6) rectangle (3.3,1);
\draw[line width=1.5pt] (-2.6,1.6) -- (-2.6,-1.1);
\draw[line width=1.5pt] (2.6,1.6) -- (2.6,-1.1);
\node[above] at (-2.6,1.6) {Zn};
\node[above] at (2.6,1.6) {Cu};
\draw (-2.6,1.6) -- (-0.9,2.3) (0.9,2.3) -- (2.6,1.6);
\draw (-0.9,2.05) rectangle (0.9,2.55);
\node at (0,2.3) {$V$};
\draw[->] (-1.7,2.3) -- (-0.95,2.3) node[above left] {$e^-$};
\draw (-1.1,0.4) .. controls (0,1.1) .. (1.1,0.4);
\node[above] at (0,0.85) {salt bridge};
\node at (-2.2,-0.7) {$Zn^{2+}$};
\node at (2.2,-0.7) {$Cu^{2+}$};
\node[below] at (-2.6,-1.6) {anode};
\node[below] at (2.6,-1.6) {cathode};
\end{tikzpicture}""",
    },
    "chem-electrolysis-cell": {
        "description": "electrolysis cell with electrolyte beaker, two electrodes, battery, ion arrows, gas bubbles and current direction",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw[thick] (-2.6,-1.5) -- (-2.6,1.2) -- (2.6,1.2) -- (2.6,-1.5);
\draw[gray] (-2.3,-0.9) rectangle (2.3,0.75);
\node[below] at (0,-1.5) {electrolyte};
\draw[line width=1.5pt] (-1.1,1.6) -- (-1.1,-0.8);
\draw[line width=1.5pt] (1.1,1.6) -- (1.1,-0.8);
\node[above] at (-1.1,1.6) {anode};
\node[above] at (1.1,1.6) {cathode};
\draw (-1.1,1.6) -- (-3.8,2.4) -- (-3.8,3.0);
\draw (1.1,1.6) -- (3.8,2.4) -- (3.8,3.0);
\draw (-4.2,3.0) -- (-3.4,3.0);
\draw (3.55,3.0) -- (4.05,3.0);
\node[above] at (-3.8,3.0) {$+$};
\node[above] at (3.8,3.0) {$-$};
\node at (0,3.0) {battery};
\draw[->] (-0.35,0.25) -- (-0.9,0.25) node[midway,above] {$A^-$};
\draw[->] (0.35,-0.25) -- (0.9,-0.25) node[midway,below] {$M^+$};
\foreach \x/\y in {-1.35/0.95,-0.95/1.15,0.95/0.95,1.35/1.15}
  \draw (\x,\y) circle (0.08);
\node[left] at (-1.7,0.95) {$O_2$};
\node[right] at (1.7,0.95) {$H_2$};
\draw[->] (2.7,2.2) -- (3.4,2.2) node[midway,below] {$I$};
\end{tikzpicture}""",
    },
    "chem-distillation-apparatus": {
        "description": "simple distillation apparatus with a boiling flask, thermometer, slanted condenser, water in and out arrows, receiver flask and a heat source",
        "tikz": r"""\begin{tikzpicture}[scale=1]
\draw ( -3.2,-1.2) circle (1.1);
\draw (-3.2,-0.1) -- (-3.2,1.0);
\draw (-3.2,1.0) -- (-1.9,1.8);
\draw (-1.9,1.8) -- (0.7,1.2);
\draw (-1.7,2.3) -- (-1.7,0.9);
\draw (-1.2,1.65) -- (1.2,1.1);
\draw (-1.05,1.95) -- (1.35,1.4);
\draw (0.1,1.25) -- (0.1,2.0);
\draw (0.75,1.55) -- (0.75,2.3);
\draw[->] (0.1,2.0) -- (0.1,2.55);
\draw[->] (0.75,2.3) -- (0.75,2.85);
\node[above] at (0.1,2.55) {water in};
\node[above] at (0.75,2.85) {water out};
\draw (1.35,1.4) -- (2.5,1.1);
\draw (2.5,1.1) -- (2.5,-0.2);
\draw (2.5,-0.2) circle (0.75);
\draw (-3.2,-2.35) arc (200:-20:0.9);
\draw[->] (-3.2,-2.2) -- (-3.2,-1.6);
\node[left] at (-3.35,-1.7) {heat};
\node[left] at (-4.1,-0.5) {flask};
\node[above] at (-1.7,2.3) {thermometer};
\node[above] at (-0.25,2.0) {condenser};
\node[right] at (3.35,-0.2) {receiver};
\end{tikzpicture}""",
    },
}
