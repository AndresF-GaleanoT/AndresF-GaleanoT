#!/usr/bin/env python3
"""Genera los SVG animados del perfil de GitHub.

    assets/hero.svg      portada: terminal + regresión lineal que se dibuja sola
    assets/notebook.svg  "sobre mí" como la salida de pandas .info()
    assets/stats.svg     actividad de GitHub analizada (se regenera a diario)

Uso:
    python scripts/generar.py          datos reales
    python scripts/generar.py --demo   datos de ejemplo, sin red

Con la variable GITHUB_TOKEN usa la API GraphQL de GitHub (así corre en
GitHub Actions). Sin token lee la página pública de contribuciones y la API
REST pública, suficiente para probar en local. Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

USUARIO = os.environ.get("GH_USER", "AndresF-GaleanoT")
SALIDA = Path(__file__).resolve().parent.parent / "assets"

# ---------------------------------------------------------------- contenido

NOMBRE = ("Andrés Felipe", "Galeano Téllez")
TERMINAL = [
    ("rol", "Ingeniero de Sistemas"),
    ("foco", "Ciencia de Datos · IA Generativa"),
    ("extra", "Ciberseguridad · Top 2% TryHackMe"),
    ("base", "Bogotá, Colombia"),
]
AREAS = [  # (área, stack, dtype)
    ("Lenguajes", "Python · SQL · R · Java", "core"),
    ("Análisis & BI", "Pandas · NumPy · Power BI", "insight"),
    ("Ingeniería de datos", "AWS · Glue · Step Functions · Iceberg", "lakehouse"),
    ("Machine Learning", "scikit-learn · YOLO · ByteTrack", "modelo"),
    ("IA Generativa", "CrewAI · NVIDIA NIM · agentes LLM", "agente"),
    ("Ciberseguridad", "Linux · OSINT · Fuzzing · TryHackMe", "exploit"),
    ("DevOps", "Docker · Kubernetes · Terraform · Git", "contenedor"),
]
TOP_LENGUAJES = 6

# ------------------------------------------------------------------- estilo

FONDO, PANEL, BORDE = "#0d1117", "#161b22", "#30363d"
TEXTO, TENUE, SEP = "#e6edf3", "#7d8590", "#3d444d"
ROSA, VIOLETA, TEAL, AMBAR = "#ff4d8d", "#a78bfa", "#2dd4bf", "#fbbf24"
NIVELES_COLOR = ["#1b222c", "#0f3d3e", "#0e6e66", "#14a38f", "#2dd4bf"]
MONO = "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,'DejaVu Sans Mono',Menlo,monospace"
SANS = "'Segoe UI','Inter',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]


def ancho(texto: str, fs: float) -> float:
    """Ancho de un texto monoespaciado (0.6 em por carácter)."""
    return round(len(texto) * fs * 0.6, 2)


def mono(x, y, texto, fs, color, extra=""):
    # textLength fija el ancho exacto: las animaciones de tecleo y las columnas
    # quedan alineadas sea cual sea la fuente monoespaciada que haya instalada.
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" fill="{color}" class="m" '
            f'textLength="{ancho(texto, fs)}" lengthAdjust="spacing"{extra}>'
            f"{escape(texto, quote=False)}</text>")


def mezcla(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    t = max(0.0, min(1.0, t))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def color_marca(t: float) -> str:
    """Color del degradado rosa → violeta → teal en la posición t (0..1)."""
    return mezcla(ROSA, VIOLETA, t * 2) if t < 0.5 else mezcla(VIOLETA, TEAL, (t - 0.5) * 2)


def svg(w, h, titulo, defs, cuerpo, estilo=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="titulo" xml:space="preserve">
<title id="titulo">{escape(titulo)}</title>
<style>
.m{{font-family:{MONO};white-space:pre}}
.s{{font-family:{SANS}}}
{estilo}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
<linearGradient id="brand" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ROSA}"/><stop offset=".5" stop-color="{VIOLETA}"/><stop offset="1" stop-color="{TEAL}"/></linearGradient>
<linearGradient id="brandMove" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="0" spreadMethod="reflect"><stop offset="0" stop-color="{ROSA}"/><stop offset=".5" stop-color="{VIOLETA}"/><stop offset="1" stop-color="{TEAL}"/><animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="{2 * w} 0" dur="9s" repeatCount="indefinite"/></linearGradient>
<clipPath id="card"><rect width="{w}" height="{h}" rx="16"/></clipPath>
{defs}
</defs>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="16" fill="{FONDO}" stroke="{BORDE}"/>
<g clip-path="url(#card)">
{cuerpo}
<rect width="{w}" height="3" fill="url(#brandMove)"/>
</g>
</svg>
"""


def aparece(inicio, dur=0.5):
    return f'<animate attributeName="opacity" from="0" to="1" begin="{inicio:.2f}s" dur="{dur}s" fill="freeze"/>'


def tecleo(ident, x, y, fs, segmentos, inicio, vel=0.022, cursor="oculta"):
    """Texto que se escribe carácter a carácter.

    segmentos: [(columna, texto, color)]. cursor: "oculta" | "parpadea".
    Devuelve (svg, instante_final).
    """
    cw = fs * 0.6
    n = max(col + len(t) for col, t, _ in segmentos)
    dur = n * vel
    fin = inicio + dur
    keys = ";".join(f"{k / (n + 1):.4f}" for k in range(n + 1))
    anchos = ";".join("0" if k == 0 else f"{k * cw + 3:.1f}" for k in range(n + 1))
    xs = ";".join(f"{x + k * cw:.1f}" for k in range(n + 1))
    tiempo = f'begin="{inicio:.2f}s" dur="{dur:.2f}s" calcMode="discrete" keyTimes="{keys}"'
    partes = [
        f'<clipPath id="{ident}"><rect x="{x - 2:.1f}" y="{y - fs:.1f}" height="{fs + 8}" width="0">'
        f'<animate attributeName="width" values="{anchos}" {tiempo} fill="freeze"/></rect></clipPath>',
        f'<g clip-path="url(#{ident})">',
        *(mono(x + col * cw, y, t, fs, color) for col, t, color in segmentos),
        "</g>",
        f'<rect x="{x:.1f}" y="{y - fs + 2:.1f}" width="{cw:.1f}" height="{fs + 2}" fill="{TEAL}" opacity="0">'
        f'<animate attributeName="x" values="{xs}" {tiempo} fill="freeze"/>'
        f'<set attributeName="opacity" to=".85" begin="{inicio:.2f}s"/>',
    ]
    if cursor == "parpadea":
        partes.append(f'<animate attributeName="opacity" values=".85;0" dur="1.1s" begin="{fin:.2f}s" '
                      f'calcMode="discrete" repeatCount="indefinite"/>')
    else:
        partes.append(f'<set attributeName="opacity" to="0" begin="{fin + 0.15:.2f}s"/>')
    partes.append("</rect>")
    return "\n".join(partes), fin


# --------------------------------------------------------------------- hero

def hero() -> str:
    W, H = 960, 320
    defs = f"""<radialGradient id="glow1" cx=".12" cy=".05" r=".55"><stop offset="0" stop-color="{ROSA}" stop-opacity=".20"/><stop offset="1" stop-color="{ROSA}" stop-opacity="0"/></radialGradient>
<radialGradient id="glow2" cx=".92" cy=".95" r=".6"><stop offset="0" stop-color="{TEAL}" stop-opacity=".16"/><stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="#ffffff" fill-opacity=".055"/></pattern>"""
    c = [f'<rect width="{W}" height="{H}" fill="url(#glow1)"/>',
         f'<rect width="{W}" height="{H}" fill="url(#glow2)"/>',
         f'<rect width="{W}" height="{H}" fill="url(#dots)"/>']

    # prompt + nombre
    prompt, t = tecleo("p0", 40, 50, 13, [(0, f"~/{USUARIO}", TEAL), (len(USUARIO) + 3, "❯", ROSA),
                                           (len(USUARIO) + 5, "whoami", TEXTO)], 0.2)
    c.append(prompt)
    c.append(f'<text x="40" y="108" class="s" font-size="48" font-weight="800" letter-spacing="-.5" '
             f'fill="{TEXTO}" opacity="0">{escape(NOMBRE[0])}{aparece(t + 0.05, 0.6)}</text>')
    c.append(f'<text x="40" y="162" class="s" font-size="48" font-weight="800" letter-spacing="-.5" '
             f'fill="url(#brand)" opacity="0">{escape(NOMBRE[1])}{aparece(t + 0.25, 0.6)}</text>')

    # líneas tipo terminal
    t += 0.5
    clave = max(len(k) for k, _ in TERMINAL) + 4
    for i, (k, v) in enumerate(TERMINAL):
        ultima = i == len(TERMINAL) - 1
        linea, t = tecleo(f"l{i}", 40, 210 + i * 26, 15, [(0, "❯", ROSA), (2, k, TEAL), (clave, v, TEXTO)],
                          t, cursor="parpadea" if ultima else "oculta")
        c.append(linea)
        t += 0.1

    # panel: datos → decisiones (regresión lineal real sobre puntos de ejemplo)
    px, py, pw, ph = 588, 34, 336, 252
    c.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="14" fill="{PANEL}" fill-opacity=".88" stroke="{BORDE}"/>')
    c.append(f'<circle cx="{px + 20}" cy="{py + 22}" r="4" fill="{TEAL}"/>')
    c.append(mono(px + 32, py + 26, "modelo.fit(datos)", 12, TEXTO))
    c.append(f'<line x1="{px}" y1="{py + 40}" x2="{px + pw}" y2="{py + 40}" stroke="{BORDE}"/>')

    x0, x1, y0, y1 = 640, 890, 244, 104          # área de datos (en píxeles)
    X = lambda u: x0 + u * (x1 - x0)
    Y = lambda v: y0 - v * (y0 - y1)
    for g in (0.33, 0.66, 1.0):
        c.append(f'<line x1="624" y1="{Y(g):.1f}" x2="904" y2="{Y(g):.1f}" stroke="{SEP}" stroke-dasharray="2 5"/>')
    c.append(f'<path d="M624 92 V252 H906" fill="none" stroke="{SEP}" stroke-width="1.2"/>')
    c.append(mono(632, 102, "decisiones", 11, TENUE))
    c.append(mono(906 - ancho("datos", 11), 270, "datos", 11, TENUE))

    rng = random.Random(7)
    n = 18
    pts = []
    for i in range(n):
        u = 0.04 + i * 0.92 / (n - 1) + rng.uniform(-0.02, 0.02)
        v = min(0.97, max(0.03, 0.12 + 0.74 * u + rng.gauss(0, 0.065)))
        pts.append((u, v))
    mu = sum(u for u, _ in pts) / n
    mv = sum(v for _, v in pts) / n
    a = sum((u - mu) * (v - mv) for u, v in pts) / sum((u - mu) ** 2 for u, _ in pts)
    b = mv - a * mu
    r2 = 1 - sum((v - (a * u + b)) ** 2 for u, v in pts) / sum((v - mv) ** 2 for _, v in pts)

    t0 = 0.6
    t_linea = t0 + n * 0.07 + 0.3
    banda = 0.09
    c.append(f'<polygon points="{X(0):.1f},{Y(b + banda):.1f} {X(1):.1f},{Y(a + b + banda):.1f} '
             f'{X(1):.1f},{Y(a + b - banda):.1f} {X(0):.1f},{Y(b - banda):.1f}" fill="url(#brand)" '
             f'fill-opacity=".10" opacity="0">{aparece(t_linea + 0.6, 0.8)}</polygon>')
    for i, (u, v) in enumerate(pts):  # residuos
        c.append(f'<line x1="{X(u):.1f}" y1="{Y(v):.1f}" x2="{X(u):.1f}" y2="{Y(a * u + b):.1f}" '
                 f'stroke="{TENUE}" stroke-width="1" stroke-dasharray="2 3" opacity="0">'
                 f'{aparece(t_linea + 0.9 + i * 0.03, 0.4)}</line>')
    for i, (u, v) in enumerate(pts):
        c.append(f'<circle cx="{X(u):.1f}" cy="{Y(v):.1f}" r="0" fill="{color_marca(u)}">'
                 f'<animate attributeName="r" values="0;6;4.2" keyTimes="0;.6;1" begin="{t0 + i * 0.07:.2f}s" '
                 f'dur=".4s" fill="freeze"/></circle>')
    lx1, ly1, lx2, ly2 = X(0), Y(b), X(1), Y(a + b)
    largo = ((lx2 - lx1) ** 2 + (ly2 - ly1) ** 2) ** 0.5
    defs += (f'\n<linearGradient id="linea" gradientUnits="userSpaceOnUse" x1="{lx1:.1f}" y1="0" x2="{lx2:.1f}" y2="0">'
             f'<stop offset="0" stop-color="{ROSA}"/><stop offset=".5" stop-color="{VIOLETA}"/>'
             f'<stop offset="1" stop-color="{TEAL}"/></linearGradient>')
    c.append(f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" stroke="url(#linea)" '
             f'stroke-width="2.6" stroke-linecap="round" stroke-dasharray="{largo:.1f}" stroke-dashoffset="{largo:.1f}">'
             f'<animate attributeName="stroke-dashoffset" from="{largo:.1f}" to="0" begin="{t_linea:.2f}s" dur="1s" '
             f'calcMode="spline" keyTimes="0;1" keySplines=".4 0 .2 1" fill="freeze"/></line>')
    # predicción que late al final de la recta
    tp = t_linea + 1.0
    c.append(f'<circle cx="{lx2:.1f}" cy="{ly2:.1f}" r="5" fill="none" stroke="{TEAL}" stroke-width="2" opacity="0">'
             f'<animate attributeName="r" values="5;16" dur="1.8s" begin="{tp:.2f}s" repeatCount="indefinite"/>'
             f'<animate attributeName="opacity" values=".9;0" dur="1.8s" begin="{tp:.2f}s" repeatCount="indefinite"/></circle>')
    c.append(f'<circle cx="{lx2:.1f}" cy="{ly2:.1f}" r="5.5" fill="{TEXTO}" stroke="{TEAL}" stroke-width="2.5" opacity="0">'
             f'{aparece(tp, 0.3)}</circle>')
    etiqueta = f"R² = {r2:.2f}"
    c.append(mono(px + pw - 18 - ancho(etiqueta, 12), py + 26, etiqueta, 12, TEAL, f' opacity="0"')
             .replace("</text>", f"{aparece(tp, 0.5)}</text>"))
    return svg(W, H, f"{' '.join(NOMBRE)}: Ingeniero de Sistemas, Ciencia de Datos, IA Generativa y Ciberseguridad",
               defs, "\n".join(c))


# ----------------------------------------------------------------- notebook

def notebook() -> str:
    W = 960
    fs, lh = 14, 22
    cw = fs * 0.6
    KW, CLS, FN, STR = "#ff7b72", "#ffa657", "#d2a8ff", "#a5d6ff"
    codigo = [
        [("from", KW), (" andres ", TEXTO), ("import", KW), (" Perfil", CLS)],
        [("yo", TEXTO), (" = ", KW), ("Perfil", CLS), (".", TEXTO), ("cargar", FN), ("(", TEXTO),
         ('"andres.parquet"', STR), (")", TEXTO)],
        [("yo", TEXTO), (".", TEXTO), ("info", FN), ("()", TEXTO)],
    ]
    c2 = 5 + max(len(a) for a, _, _ in AREAS) + 2
    c3 = c2 + max(len(s) for _, s, _ in AREAS) + 2
    salida = [
        [(0, "<class 'andres.Perfil'>", TENUE)],
        [(0, f"RangeIndex: {len(AREAS)} entradas, 0 a {len(AREAS) - 1}", TENUE)],
        [(0, "Data columns (total 3 columns):", TENUE)],
        [(1, "#", TEXTO), (5, "Área", TEXTO), (c2, "Stack", TEXTO), (c3, "Dtype", TEXTO)],
        [(0, "---", SEP), (5, "-" * (c2 - 7), SEP), (c2, "-" * (c3 - c2 - 2), SEP), (c3, "-" * 10, SEP)],
        *[[(1, str(i), TENUE), (5, a, TEXTO), (c2, s, "#9fe8dc"), (c3, d, VIOLETA)]
          for i, (a, s, d) in enumerate(AREAS)],
        [(0, "dtypes: café(1), curiosidad(int64), datos(∞)", TENUE)],
        [(0, "memory usage: creciendo cada día", TENUE)],
    ]
    y_cod = 62
    alto_cod = len(codigo) * lh + 22
    y_sal = y_cod + alto_cod + 36
    H = y_sal + (len(salida) - 1) * lh + 34

    t_corre, t_fin = 0.6, 1.6
    c = [f'<rect width="{W}" height="44" fill="{PANEL}"/>',
         f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{BORDE}"/>',
         f'<rect x="24" y="10" width="172" height="35" rx="8" fill="{FONDO}" stroke="{BORDE}"/>',
         f'<rect x="25" y="44" width="170" height="2" fill="{FONDO}"/>',
         f'<rect x="32" y="10" width="156" height="2" rx="1" fill="url(#brand)"/>',
         f'<rect x="40" y="22" width="12" height="12" rx="3" fill="{AMBAR}"/>',
         mono(62, 32, "perfil.ipynb", 12.5, TEXTO)]
    kernel = "Python 3 (ipykernel)"
    c.append(mono(W - 46 - ancho(kernel, 12), 31, kernel, 12, TENUE))
    c.append(f'<circle cx="{W - 32}" cy="27" r="6" fill="none" stroke="{TENUE}" stroke-width="1.6">'
             f'<set attributeName="fill" to="{TENUE}" begin="{t_corre}s"/>'
             f'<set attributeName="fill" to="none" begin="{t_fin}s"/></circle>')

    # celda de código
    for etiqueta, desde, hasta in (("In [ ]:", None, t_corre), ("In [*]:", t_corre, t_fin), ("In [1]:", t_fin, None)):
        anim = ""
        if desde is not None:
            anim += f'<set attributeName="opacity" to="1" begin="{desde}s"/>'
        if hasta is not None:
            anim += f'<set attributeName="opacity" to="0" begin="{hasta}s"/>'
        op = "1" if desde is None else "0"
        c.append(mono(36, y_cod + 26, etiqueta, 13, VIOLETA, f' opacity="{op}"').replace("</text>", anim + "</text>"))
    c.append(f'<rect x="110" y="{y_cod}" width="{W - 150}" height="{alto_cod}" rx="8" fill="{PANEL}" stroke="{BORDE}"/>')
    c.append(f'<rect x="96" y="{y_cod}" width="3" height="{alto_cod}" rx="1.5" fill="{TEAL}"/>')
    for i, tokens in enumerate(codigo):
        col = 0
        for texto, color in tokens:
            c.append(mono(128 + col * cw, y_cod + 26 + i * lh, texto, fs, color))
            col += len(texto)

    # salida de .info()
    c.append(f'<rect x="96" y="{y_sal - 22}" width="3" height="{(len(salida) - 1) * lh + 30}" rx="1.5" '
             f'fill="{SEP}" class="up" style="animation-delay:{t_fin}s"/>')
    for i, fila in enumerate(salida):
        y = y_sal + i * lh
        piezas = "".join(mono(128 + col * cw, y, t, fs, color) for col, t, color in fila)
        c.append(f'<g class="up" style="animation-delay:{t_fin + 0.1 + i * 0.09:.2f}s">{piezas}</g>')

    estilo = """@keyframes up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.up{animation:up .45s cubic-bezier(.2,.7,.2,1) both}"""
    return svg(W, H, "Sobre mí, como la salida de pandas .info(): " +
               "; ".join(f"{a}: {s}" for a, s, _ in AREAS), "", "\n".join(c), estilo)


# ------------------------------------------------------------------ datos

def _get(url: str, token: str | None = None, data: bytes | None = None) -> str:
    cabeceras = {"User-Agent": "perfil-svg", "Accept": "application/vnd.github+json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=cabeceras)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


CONSULTA = """query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionCalendar { weeks { contributionDays {
      date contributionCount contributionLevel } } } }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
        edges { size node { name color } } } } }
  }
}"""
NIVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
COLORES_LENG = {"Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Java": "#b07219",
                "HTML": "#e34c26", "CSS": "#663399", "Shell": "#89e051", "HCL": "#844FBA", "R": "#198CE7",
                "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384d54", "SQL": "#e38c00"}


def datos_graphql(token: str):
    cuerpo = json.dumps({"query": CONSULTA, "variables": {"login": USUARIO}}).encode()
    res = json.loads(_get("https://api.github.com/graphql", token, cuerpo))
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    u = res["data"]["user"]
    semanas = u["contributionsCollection"]["contributionCalendar"]["weeks"]
    dias = [(dt.date.fromisoformat(d["date"]), d["contributionCount"], NIVEL[d["contributionLevel"]])
            for s in semanas for d in s["contributionDays"]]
    leng: dict[str, list] = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            nombre, color = e["node"]["name"], e["node"]["color"]
            fila = leng.setdefault(nombre, [0, color])
            fila[0] += e["size"]
    return dias, {k: (v[0], v[1]) for k, v in leng.items()}


def _atributos(etiqueta: str) -> dict:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', etiqueta))


def datos_publicos():
    html = _get(f"https://github.com/users/{USUARIO}/contributions")
    conteo = {}
    for attrs, texto in re.findall(r"<tool-tip ([^>]*)>([^<]*)</tool-tip>", html):
        m = re.match(r"\s*([\d,]+) contribution", texto)
        conteo[_atributos(attrs).get("for")] = int(m.group(1).replace(",", "")) if m else 0
    dias = []
    for etiqueta in re.findall(r"<td [^>]*ContributionCalendar-day[^>]*>", html):
        a = _atributos(etiqueta)
        if "data-date" in a:
            dias.append((dt.date.fromisoformat(a["data-date"]), conteo.get(a.get("id"), 0),
                         int(a.get("data-level", 0))))
    if not dias:
        raise RuntimeError("No se pudo leer el calendario público de contribuciones")
    leng: dict[str, tuple] = {}
    try:
        repos = json.loads(_get(f"https://api.github.com/users/{USUARIO}/repos?per_page=100&type=owner"))
        for r in repos:
            if r["fork"] or r.get("private"):
                continue
            for nombre, tam in json.loads(_get(r["languages_url"])).items():
                previo = leng.get(nombre, (0, COLORES_LENG.get(nombre)))
                leng[nombre] = (previo[0] + tam, previo[1])
    except urllib.error.HTTPError as e:  # límite de la API sin token: se omiten los lenguajes
        print(f"Aviso: lenguajes omitidos ({e.code})")
        leng = {}
    return dias, leng


def datos_demo():
    rng = random.Random(42)
    hoy = dt.date.today()
    dias = []
    for k in range(370, -1, -1):
        d = hoy - dt.timedelta(days=k)
        activo = rng.random() < (0.55 if d.weekday() < 5 else 0.25)
        n = int(rng.expovariate(0.25)) + 1 if activo else 0
        dias.append((d, n, 0))
    positivos = sorted(n for _, n, _ in dias if n)
    cortes = [positivos[int(len(positivos) * q)] for q in (0.25, 0.5, 0.75)]
    dias = [(d, n, 0 if n == 0 else 1 + sum(n > c for c in cortes)) for d, n, _ in dias]
    leng = {"Python": (520_000, "#3572A5"), "TypeScript": (210_000, "#3178c6"), "Java": (90_000, "#b07219"),
            "JavaScript": (70_000, "#f1e05a"), "HTML": (40_000, "#e34c26"), "Shell": (15_000, "#89e051"),
            "HCL": (9_000, "#844FBA"), "Dockerfile": (2_000, "#384d54")}
    return dias, leng


# ------------------------------------------------------------- estadísticas

def fnum(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def ffecha(d: dt.date) -> str:
    return f"{d.day} {MESES[d.month - 1]}"


def resumen(dias):
    total = sum(c for _, c, _ in dias)
    i = len(dias) - 1
    if i >= 0 and dias[i][1] == 0:  # hoy sin contribuciones aún no rompe la racha
        i -= 1
    actual = 0
    while i >= 0 and dias[i][1] > 0:
        actual += 1
        i -= 1
    mejor, rango, corrida, desde = 0, None, 0, None
    for d, c, _ in dias:
        if c > 0:
            desde = d if corrida == 0 else desde
            corrida += 1
            if corrida > mejor:
                mejor, rango = corrida, (desde, d)
        else:
            corrida = 0
    por_dia = [0] * 7  # 0 = domingo
    for d, c, _ in dias:
        por_dia[(d.weekday() + 1) % 7] += c
    return total, actual, mejor, rango, por_dia


def claro(color: str | None) -> str:
    """Aclara los colores de lenguaje demasiado oscuros para el fondo."""
    if not color:
        return TENUE
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return mezcla(color, "#ffffff", 0.45) if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.25 else color


def stats(dias, leng) -> str:
    dias = sorted(dias)
    total, actual, mejor, rango, por_dia = resumen(dias)
    hoy = dias[-1][0]
    W = 960
    c = []

    comando = [(0, "❯", ROSA), (2, "python", TEXTO), (9, f"scripts/generar.py --user {USUARIO}", TENUE)]
    c.append("".join(mono(40 + col * 12 * 0.6, 34, t, 12, color) for col, t, color in comando))
    fecha = f"datos al {ffecha(hoy)} {hoy.year}"
    c.append(mono(W - 40 - ancho(fecha, 12), 34, fecha, 12, TENUE))

    # KPI
    top = max(range(7), key=lambda k: por_dia[k])
    activos = sum(1 for _, n, _ in dias if n)
    kpis = [
        ("CONTRIBUCIONES", fnum(total), "últimos 12 meses"),
        ("RACHA ACTUAL", str(actual), "día seguido" if actual == 1 else "días seguidos") if actual else
        ("DÍAS ACTIVOS", str(activos), f"{activos * 100 // len(dias)}% del año"),
        ("RACHA MÁS LARGA", str(mejor), f"{ffecha(rango[0])} → {ffecha(rango[1])}" if rango else "—"),
        ("DÍA MÁS ACTIVO", DIAS[top] if total else "—", f"{fnum(por_dia[top])} contribuciones"),
    ]
    tw, gap, ty = (W - 80 - 3 * 16) / 4, 16, 54
    for k, (etq, valor, sub) in enumerate(kpis):
        x = 40 + k * (tw + gap)
        c.append(f'<g class="up" style="animation-delay:{0.1 + k * 0.1:.1f}s">'
                 f'<rect x="{x:.1f}" y="{ty}" width="{tw:.1f}" height="84" rx="12" fill="{PANEL}" stroke="{BORDE}"/>'
                 f'{mono(x + 16, ty + 24, etq, 11, TENUE)}'
                 f'<text x="{x + 16:.1f}" y="{ty + 58}" class="s" font-size="30" font-weight="800" fill="url(#brand)">'
                 f'{escape(valor)}</text>{mono(x + 16, ty + 75, sub, 11, TENUE)}</g>')

    # heatmap
    domingo0 = dias[0][0] - dt.timedelta(days=(dias[0][0].weekday() + 1) % 7)
    celdas = [((d - domingo0).days // 7, (d.weekday() + 1) % 7, d, n, nv) for d, n, nv in dias]
    ncols = max(cl for cl, *_ in celdas) + 1
    gx, gy, area = 64, 192, 742
    paso = min(14.0, area / ncols)
    lado = paso - 3
    c.append(mono(40, 166, "calendario.heatmap()", 11, TENUE))
    primer_mes = {}
    for cl, _, d, _, _ in sorted(celdas):
        primer_mes.setdefault(cl, d.month)
    marcas, previo = [], None
    for cl in range(ncols):
        if cl in primer_mes and primer_mes[cl] != previo:
            marcas.append((cl, primer_mes[cl]))
            previo = primer_mes[cl]
    for (cl, mes), siguiente in zip(marcas, marcas[1:] + [(ncols + 3, 0)]):
        if siguiente[0] - cl >= 3:
            c.append(mono(gx + cl * paso, gy - 8, MESES[mes - 1], 10, TENUE))
    for fila, nombre in ((1, "lun"), (3, "mié"), (5, "vie")):
        c.append(mono(40, gy + fila * paso + lado - 1.5, nombre, 9, TENUE))
    pico = max(dias, key=lambda t: (t[1], t[0]))
    for cl, fila, d, n, nv in celdas:
        x, y = gx + cl * paso, gy + fila * paso
        es_pico = n > 0 and d == pico[0]
        trazo = f' stroke="{ROSA}" stroke-width="1.5"' if es_pico else ""
        c.append(f'<rect class="d w{cl}" x="{x:.1f}" y="{y:.1f}" width="{lado:.1f}" height="{lado:.1f}" rx="2.5" '
                 f'fill="{NIVELES_COLOR[nv]}"{trazo}/>')
        if es_pico:
            c.append(f'<rect class="pk" x="{x:.1f}" y="{y:.1f}" width="{lado:.1f}" height="{lado:.1f}" rx="2.5" '
                     f'fill="none" stroke="{ROSA}" stroke-width="1.5"/>')
    # leyenda de niveles
    ly = gy + 7 * paso + 14
    c.append(mono(gx, ly + 8, "menos", 9, TENUE))
    for k, color in enumerate(NIVELES_COLOR):
        c.append(f'<rect x="{gx + 34 + k * 13}" y="{ly}" width="10" height="10" rx="2" fill="{color}"/>')
    c.append(mono(gx + 34 + 5 * 13 + 4, ly + 8, "más", 9, TENUE))
    if pico[1]:
        nota = f"pico: {pico[1]} el {ffecha(pico[0])}"
        c.append(f'<rect x="{gx + 130}" y="{ly}" width="10" height="10" rx="2" fill="none" stroke="{ROSA}" stroke-width="1.5"/>')
        c.append(mono(gx + 146, ly + 8, nota, 9, TENUE))

    # barras por día de la semana
    bx = gx + area + 30
    c.append(mono(bx, 166, "por_dia", 11, TENUE))
    maximo = max(max(por_dia), 1)
    orden = [1, 2, 3, 4, 5, 6, 0]  # de lunes a domingo
    for fila, k in enumerate(orden):
        y = gy + fila * paso
        largo = por_dia[k] / maximo * 40
        c.append(mono(bx, y + lado - 1.5, "LMXJVSD"[fila], 9, TENUE))
        c.append(f'<rect x="{bx + 12}" y="{y:.1f}" width="0" height="{lado:.1f}" rx="2.5" '
                 f'fill="{AMBAR if k == top else TEAL}" fill-opacity="{1 if k == top else 0.75}">'
                 f'<animate attributeName="width" from="0" to="{max(largo, 2):.1f}" begin="{0.9 + fila * 0.06:.2f}s" '
                 f'dur=".7s" calcMode="spline" keyTimes="0;1" keySplines=".2 .7 .2 1" fill="freeze"/></rect>')
        etq = str(por_dia[k])
        c.append(f'<g class="up" style="animation-delay:{1.4 + fila * 0.06:.2f}s">'
                 f'{mono(bx + 12 + max(largo, 2) + 5, y + lado - 1.5, etq, 9, TENUE)}</g>')
    H = ly + 28

    # lenguajes
    if leng:
        total_b = sum(v[0] for v in leng.values())
        orden_l = sorted(leng.items(), key=lambda kv: -kv[1][0])
        partes = [(n, v[0], claro(v[1])) for n, v in orden_l[:TOP_LENGUAJES]]
        resto = sum(v[0] for _, v in orden_l[TOP_LENGUAJES:])
        if resto:
            partes.append(("Otros", resto, TENUE))
        y0 = H + 18
        c.append(mono(40, y0, "lenguajes.value_counts(normalize=True)", 11, TENUE))
        bw, x = W - 80, 40.0
        segs = []
        for n, b, color in partes:
            w = b / total_b * bw
            segs.append(f'<rect x="{x:.1f}" y="{y0 + 12}" width="{max(w - 2, 1):.1f}" height="10" fill="{color}"/>')
            x += w
        c.append(f'<clipPath id="barra"><rect x="40" y="{y0 + 12}" height="10" rx="5" width="0">'
                 f'<animate attributeName="width" from="0" to="{bw}" begin="1.2s" dur="1.2s" calcMode="spline" '
                 f'keyTimes="0;1" keySplines=".4 0 .2 1" fill="freeze"/></rect></clipPath>')
        c.append(f'<g clip-path="url(#barra)">{"".join(segs)}</g>')
        x, y = 40.0, y0 + 46
        for k, (n, b, color) in enumerate(partes):
            pct = f"{b / total_b * 100:.1f}%"
            ancho_item = 14 + ancho(n, 12) + 6 + ancho(pct, 12) + 22
            if x + ancho_item > W - 40:
                x, y = 40.0, y + 22
            c.append(f'<g class="up" style="animation-delay:{1.6 + k * 0.07:.2f}s">'
                     f'<circle cx="{x + 5:.1f}" cy="{y - 4}" r="5" fill="{color}"/>'
                     f'{mono(x + 14, y, n, 12, TEXTO)}{mono(x + 20 + ancho(n, 12), y, pct, 12, TENUE)}</g>')
            x += ancho_item
        H = y + 26

    estilo = "\n".join([
        "@keyframes up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}",
        "@keyframes pop{from{opacity:0;transform:scale(.2)}to{opacity:1;transform:scale(1)}}",
        "@keyframes pulso{from{opacity:.9;transform:scale(1)}to{opacity:0;transform:scale(2.6)}}",
        ".up{animation:up .5s cubic-bezier(.2,.7,.2,1) both}",
        ".d{transform-box:fill-box;transform-origin:center;animation:pop .45s ease-out both}",
        ".pk{opacity:0;transform-box:fill-box;transform-origin:center;animation:pulso 1.8s ease-out 2.2s infinite}",
        "".join(f".w{k}{{animation-delay:{0.3 + k * 0.018:.3f}s}}" for k in range(ncols)),
    ])
    titulo = (f"Actividad de {USUARIO} en GitHub: {fnum(total)} contribuciones en 12 meses, "
              f"racha actual de {actual} días, racha más larga de {mejor} días")
    return svg(W, round(H), titulo, "", "\n".join(c), estilo)


# --------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true", help="usar datos de ejemplo (sin red)")
    args = p.parse_args()

    if args.demo:
        dias, leng = datos_demo()
    elif token := os.environ.get("GITHUB_TOKEN"):
        dias, leng = datos_graphql(token)
    else:
        dias, leng = datos_publicos()

    SALIDA.mkdir(exist_ok=True)
    for nombre, contenido in (("hero.svg", hero()), ("notebook.svg", notebook()), ("stats.svg", stats(dias, leng))):
        (SALIDA / nombre).write_text(contenido, encoding="utf-8", newline="\n")
        print(f"assets/{nombre}  {len(contenido) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
