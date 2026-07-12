# -*- coding: utf-8 -*-
"""Build the one-page HTML analysis report for Uschriften_clean.csv.

v2: reads enrichment columns persisted by kreis_pipeline.py
(bundesland, kreis_ags, ost_west, geschlecht_geschaetzt) and adds a
Kreis-level section (politics, deprivation, East/West, university effect).
"""
import pandas as pd
import numpy as np
import json
import re
import math

SCRATCH = "/private/tmp/claude-501/-Users-admin-Desktop-hyperadapted/68cc7daa-4deb-45a3-b7b0-dab25a8802db/scratchpad"
PSY = "/Users/admin/Desktop/psytition"
SRC = f"{PSY}/Uschriften_clean.csv"
KREIS_STATS = f"{PSY}/kreis_stats.csv"
GEO_STATES = f"{SCRATCH}/bundeslaender.geojson"
GEO_KREISE = f"{SCRATCH}/georef_kreise.geojson"
OUT = f"{PSY}/Uschriften_report.html"

POP = {
    "Nordrhein-Westfalen": 18_139_000, "Bayern": 13_369_000, "Baden-Württemberg": 11_280_000,
    "Niedersachsen": 8_140_000, "Hessen": 6_391_000, "Rheinland-Pfalz": 4_159_000,
    "Sachsen": 4_086_000, "Berlin": 3_755_000, "Schleswig-Holstein": 2_953_000,
    "Brandenburg": 2_573_000, "Sachsen-Anhalt": 2_187_000, "Thüringen": 2_127_000,
    "Hamburg": 1_892_000, "Mecklenburg-Vorpommern": 1_628_000, "Saarland": 993_000,
    "Bremen": 685_000,
}
CODE = {"Baden-Württemberg": "BW", "Bayern": "BY", "Berlin": "BE", "Brandenburg": "BB",
        "Bremen": "HB", "Hamburg": "HH", "Hessen": "HE", "Mecklenburg-Vorpommern": "MV",
        "Niedersachsen": "NI", "Nordrhein-Westfalen": "NW", "Rheinland-Pfalz": "RP",
        "Saarland": "SL", "Sachsen-Anhalt": "ST", "Sachsen": "SN",
        "Schleswig-Holstein": "SH", "Thüringen": "TH"}

df = pd.read_csv(SRC, dtype=str).fillna("")
n_total = len(df)
K = pd.read_csv(KREIS_STATS, dtype={"kreis_ags": str}).set_index("kreis_ags")

# ---------------------------------------------------------------- time
ts = pd.to_datetime(df["createdAt"], utc=True).dt.tz_convert("Europe/Berlin")
WD = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}
hourly = ts.dt.floor("h").value_counts().sort_index()
hour_labels = [f"{WD[t.weekday()]} {t.strftime('%H')}h" for t in hourly.index]
hour_counts = hourly.tolist()
cum_counts = hourly.cumsum().tolist()
from collections import Counter
slot_occ = Counter(t.hour for t in pd.date_range(ts.min().floor("h"), ts.max().floor("h"), freq="h"))
slot_sum = ts.dt.hour.value_counts().to_dict()
hod = [round(slot_sum.get(h, 0) / max(slot_occ.get(h, 1), 1)) for h in range(24)]
first24 = (ts < ts.min() + pd.Timedelta(hours=24)).mean()
day_counts = ts.dt.date.value_counts().sort_index()
_dpk = day_counts.idxmax()
day_peak = f"{WD[pd.Timestamp(_dpk).weekday()]}, {_dpk.strftime('%d.%m.')}"
peak_t = hourly.idxmax()
peak_label = f"{WD[peak_t.weekday()]} {peak_t.strftime('%d.%m., %H')}–{(peak_t.hour + 1) % 24} Uhr"
span_h = (ts.max() - ts.min()).total_seconds() / 3600

# ---------------------------------------------------------------- persisted enrichment
state_counts = df.loc[df["bundesland"] != "", "bundesland"].value_counts().to_dict()
geo_cov = (df["bundesland"] != "").mean()
kreis_cov = (df["kreis_ags"] != "").mean()
per100k_state = {s: state_counts.get(s, 0) / POP[s] * 100_000 for s in POP}

gender = df["geschlecht_geschaetzt"]
n_f, n_m, n_u = (gender == "f").sum(), (gender == "m").sum(), (gender == "").sum()
fem_share = n_f / (n_f + n_m)

cat_counts = df["berufskategorie"].value_counts()
title_share = (df["has_academic_title"] == "yes").mean()
top_titles = df.loc[df["academicTitle"] != "", "academicTitle"].value_counts().head(10)
top_cities = df.loc[df["ort"] != "", "ort"].value_counts().head(15)
top_jobs = df.loc[~df["berufskategorie"].isin(["Unbekannt"]), "berufsbezeichnung"].value_counts().head(12)
fach = df["berufskategorie"].isin(["Psychotherapie & Psychologie", "Medizin & Pflege",
                                   "Gesundheitswesen (sonstige)", "Soziale Arbeit & Erziehung"]).mean()
psych_share = (df["berufskategorie"] == "Psychotherapie & Psychologie").mean()
stud_share = (df["berufskategorie"] == "Student:in").mean()
psych_title = (df.loc[df["berufskategorie"] == "Psychotherapie & Psychologie", "has_academic_title"] == "yes").mean()

# ---------------------------------------------------------------- kreis analysis numbers
A = K.dropna(subset=["gisd_score", "share_Gruene"]).copy()
A = A[A["per100k"] > 0]
A["log_density"] = np.log10(A["density"])
rho = {c: A["per100k"].corr(A[c], method="spearman")
       for c in ["share_Gruene", "share_AfD", "share_Linke", "gisd_score", "log_density"]}

afd_q = pd.qcut(A["share_AfD"], 5, labels=False)
afd_lo = A.loc[afd_q == 0, "per100k"].mean()
afd_hi = A.loc[afd_q == 4, "per100k"].mean()

grp = K.groupby("ost_west")[["per100k", "psych_per100k", "nonpsych_per100k"]].mean()
uni_med = K.groupby("uni_psych")["per100k"].median()
east_uni = K[(K["ost_west"] == "Ost") & K["uni_psych"]]["per100k"].median()
east_nouni = K[(K["ost_west"] == "Ost") & ~K["uni_psych"]]["per100k"].median()
west_nouni = K[(K["ost_west"] == "West") & ~K["uni_psych"]]["per100k"].median()

# standardized OLS
X_cols = ["share_Gruene", "share_AfD", "gisd_score", "log_density"]
A["east"] = (A["ost_west"] == "Ost").astype(float)
Xz = (A[X_cols + ["east"]] - A[X_cols + ["east"]].mean()) / A[X_cols + ["east"]].std()
yz = (np.log10(A["per100k"]) - np.log10(A["per100k"]).mean()) / np.log10(A["per100k"]).std()
Xm = np.column_stack([np.ones(len(A)), Xz.values])
beta, *_ = np.linalg.lstsq(Xm, yz.values, rcond=None)
r2 = 1 - ((yz.values - Xm @ beta) ** 2).sum() / ((yz.values - yz.values.mean()) ** 2).sum()
betas = dict(zip(X_cols + ["east"], beta[1:]))

top15 = K.nlargest(15, "per100k")

# ---------------------------------------------------------------- projection (shared)
geo_st = json.load(open(GEO_STATES))
LAT_M = math.cos(math.radians(51.0))
def project(lon, lat, scale, ox, oy):
    return (lon * LAT_M * scale + ox, -lat * scale + oy)

all_pts = []
for f in geo_st["features"]:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for poly in polys:
        all_pts.extend(poly[0])
lons = [p[0] for p in all_pts]; lats = [p[1] for p in all_pts]
W, H = 380, 500
scale = min(W / ((max(lons) - min(lons)) * LAT_M), H / (max(lats) - min(lats))) * 0.95
ox = -min(lons) * LAT_M * scale + (W - (max(lons) - min(lons)) * LAT_M * scale) / 2
oy = max(lats) * scale + (H - (max(lats) - min(lats)) * scale) / 2

def hexmix(a, b, t):
    av = [int(a[i:i+2], 16) for i in (1, 3, 5)]
    bv = [int(b[i:i+2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(av[i] + (bv[i] - av[i]) * t):02x}" for i in range(3))

def rings_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            yield ring

def path_d(geom, decimate=1):
    d = ""
    for ring in rings_of(geom):
        pts = ring[::decimate] if len(ring) > 240 else ring
        proj = [project(x, y, scale, ox, oy) for x, y in pts]
        # drop consecutive duplicates after rounding
        out, last = [], None
        for x, y in proj:
            p = (round(x, 1), round(y, 1))
            if p != last:
                out.append(p)
                last = p
        if len(out) >= 3:
            d += "M" + "L".join(f"{x},{y}" for x, y in out) + "Z"
    return d

def feat_extent(geom):
    xs = [p[0] for ring in rings_of(geom) for p in ring]
    ys = [p[1] for ring in rings_of(geom) for p in ring]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))

def make_state_map(values, fmt):
    vmax, vmin = max(values.values()), min(values.values())
    paths, labels = [], []
    for f in sorted(geo_st["features"], key=lambda f: feat_extent(f["geometry"]), reverse=True):
        name = f["properties"]["name"]
        d = path_d(f["geometry"])
        t = (values[name] - vmin) / (vmax - vmin) if vmax > vmin else 0
        fill = hexmix("#f2ede3", "#c2371f", 0.08 + 0.92 * t)
        big = max(rings_of(f["geometry"]), key=len)
        cx = sum(project(x, y, scale, ox, oy)[0] for x, y in big) / len(big)
        cy = sum(project(x, y, scale, ox, oy)[1] for x, y in big) / len(big)
        paths.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd" stroke="#faf9f6" stroke-width="1">'
                     f'<title>{name}: {fmt(values[name])}</title></path>')
        if name not in ("Bremen", "Berlin", "Hamburg", "Saarland"):
            lab = "#faf9f6" if t > 0.55 else "#4a453d"
            labels.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="10" text-anchor="middle" fill="{lab}" style="pointer-events:none">{CODE[name]}</text>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">' + "".join(paths) + "".join(labels) + "</svg>"

def fmtn(x): return f"{x:,.0f}".replace(",", ".")
map_abs = make_state_map({s: state_counts.get(s, 0) for s in POP}, lambda v: fmtn(v))
map_rel = make_state_map(per100k_state, lambda v: f"{fmtn(v)} je 100k")

state_rows = sorted(POP, key=lambda s: -per100k_state[s])
state_table = "".join(
    f"<tr><td>{s}</td><td class='num'>{fmtn(state_counts.get(s, 0))}</td><td class='num'>{fmtn(per100k_state[s])}</td>"
    f"<td><div class='bar' style='width:{per100k_state[s]/max(per100k_state.values())*100:.0f}%'></div></td></tr>"
    for s in state_rows)

# ---------------------------------------------------------------- kreis map (percentile colors)
geo_k = json.load(open(GEO_KREISE))
ranks = K["per100k"].rank(pct=True)
kpaths = []
for f in sorted(geo_k["features"], key=lambda f: feat_extent(f["geometry"]), reverse=True):
    ags = f["properties"]["krs_code"]
    ags = ags[0] if isinstance(ags, list) else ags
    if ags not in K.index:
        continue
    pct = ranks.get(ags, 0.5)
    fill = hexmix("#f2ede3", "#c2371f", 0.04 + 0.96 * float(pct))
    name = K.loc[ags, "kreis_name"] if pd.notna(K.loc[ags, "kreis_name"]) else ags
    tip = f"{name}: {fmtn(K.loc[ags, 'per100k'])} je 100k ({fmtn(K.loc[ags, 'signatures'])} Unterschriften)"
    kpaths.append(f'<path d="{path_d(f["geometry"], decimate=2)}" fill="{fill}" fill-rule="evenodd" '
                  f'stroke="#faf9f6" stroke-width="0.4"><title>{tip}</title></path>')
map_kreise = f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">' + "".join(kpaths) + "</svg>"

def short_name(n):
    n = str(n)
    n = re.sub(r",.*$", "", n)
    return n
top15_rows = "".join(
    f"<tr><td>{short_name(r.kreis_name)}"
    + (" <span class='tag'>Uni-Psych</span>" if r.uni_psych else "")
    + (" <span class='tag ost'>Ost</span>" if r.ost_west == "Ost" else "")
    + f"</td><td class='num'>{fmtn(r.signatures)}</td><td class='num'>{fmtn(r.per100k)}</td>"
    f"<td><div class='bar' style='width:{r.per100k/top15['per100k'].max()*100:.0f}%'></div></td></tr>"
    for r in top15.itertuples())

# ---------------------------------------------------------------- payload
GROUP_COLOR = {"West": "#3d5a80", "Ost": "#c2371f", "Berlin": "#171512"}
def scatter_data(xcol):
    return [{"x": round(float(r[xcol]), 1), "y": round(float(r["per100k"])),
             "n": short_name(r["kreis_name"]), "g": r["ost_west"]}
            for _, r in A.iterrows()]

payload = {
    "hourLabels": hour_labels, "hourCounts": hour_counts, "cumCounts": cum_counts, "hod": hod,
    "catLabels": cat_counts.index.tolist(), "catCounts": cat_counts.tolist(),
    "genderLabels": ["Frauen", "Männer", "unbestimmt"], "genderCounts": [int(n_f), int(n_m), int(n_u)],
    "titleLabels": top_titles.index.tolist(), "titleCounts": top_titles.tolist(),
    "cityLabels": top_cities.index.tolist(), "cityCounts": top_cities.tolist(),
    "jobLabels": top_jobs.index.tolist(), "jobCounts": top_jobs.tolist(),
    "scAfD": scatter_data("share_AfD"), "scGruene": scatter_data("share_Gruene"),
    "scGisd": [{"x": round(float(r["gisd_score"]), 3), "y": round(float(r["per100k"])),
                "n": short_name(r["kreis_name"]), "g": r["ost_west"]} for _, r in A.iterrows()],
    "scDens": [{"x": round(float(r["density"])), "y": round(float(r["per100k"])),
                "n": short_name(r["kreis_name"]), "g": r["ost_west"]} for _, r in A.iterrows()],
    "groupColor": GROUP_COLOR,
    "owLabels": ["West", "Ost", "Berlin"],
    "owPsych": [round(grp.loc[g, "psych_per100k"], 1) for g in ["West", "Ost", "Berlin"]],
    "owNon": [round(grp.loc[g, "nonpsych_per100k"], 1) for g in ["West", "Ost", "Berlin"]],
    "uniLabels": ["Kreise mit Psychologie-Uni", "übrige Kreise"],
    "uniMed": [round(uni_med[True]), round(uni_med[False])],
}

html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unterschriften-Analyse — 480.000 Signaturen</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {{ --ink:#171512; --muted:#7a7468; --accent:#c2371f; --bg:#faf9f6; --line:#e6e1d6; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system, "Helvetica Neue", Segoe UI, sans-serif; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:48px 28px 80px; }}
  header h1 {{ font-size:34px; line-height:1.15; margin:0 0 6px; letter-spacing:-.5px; }}
  header p.sub {{ color:var(--muted); margin:0 0 28px; max-width:72ch; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:14px; }}
  .kpi {{ border:1px solid var(--line); background:#fff; border-radius:10px; padding:14px 16px; }}
  .kpi b {{ display:block; font-size:26px; letter-spacing:-.5px; }}
  .kpi span {{ color:var(--muted); font-size:12.5px; }}
  .insights {{ background:#fff; border:1px solid var(--line); border-left:3px solid var(--accent);
               border-radius:0 10px 10px 0; padding:16px 20px; margin:14px 0 34px; }}
  .insights ul {{ margin:6px 0 0; padding-left:18px; }}
  .insights li {{ margin:5px 0; }}
  h2 {{ font-size:20px; margin:38px 0 4px; letter-spacing:-.3px; }}
  h2 + p {{ color:var(--muted); margin:0 0 16px; font-size:13.5px; max-width:80ch; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  .card {{ border:1px solid var(--line); background:#fff; border-radius:10px; padding:18px 18px 12px; }}
  .card h3 {{ margin:0 0 2px; font-size:15px; }}
  .card p {{ margin:0 0 10px; color:var(--muted); font-size:12.5px; }}
  .card.wide {{ grid-column:1 / -1; }}
  .chartbox {{ position:relative; height:260px; }}
  .chartbox.tall {{ height:420px; }}
  .maps {{ display:grid; grid-template-columns:1fr 1fr 1.2fr; gap:18px; align-items:start; }}
  .mapcard svg {{ width:100%; height:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  td {{ padding:4px 8px 4px 0; border-bottom:1px solid var(--line); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .bar {{ height:8px; background:var(--accent); border-radius:4px; min-width:2px; }}
  .tag {{ font-size:10px; background:#3d5a8022; color:#3d5a80; border-radius:4px; padding:1px 5px; white-space:nowrap; }}
  .tag.ost {{ background:#c2371f18; color:var(--accent); }}
  .legend {{ display:flex; gap:14px; font-size:12px; color:var(--muted); margin:4px 0 8px; flex-wrap:wrap; }}
  .legend i {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; }}
  footer {{ margin-top:44px; color:var(--muted); font-size:12.5px; border-top:1px solid var(--line); padding-top:14px; }}
  @media (max-width:820px) {{ .grid, .maps {{ grid-template-columns:1fr; }} }}
</style></head><body><div class="wrap">

<header>
  <h1>480.000 Unterschriften in 60 Stunden</h1>
  <p class="sub">Explorative Analyse der Petitions-Signaturen ({ts.min().strftime('%d.%m.')}&ndash;{ts.max().strftime('%d.%m.%Y')},
  Zeiten in Europe/Berlin) — jetzt mit Kreisebene: Wahlergebnisse (BTW 2025), sozioökonomische Deprivation (RKI GISD),
  Ost/West und Urbanität. Grundlage: <code>Uschriften_clean.csv</code> + <code>kreis_stats.csv</code>.
  Alle demografischen Angaben sind Näherungen aus Selbstauskünften.</p>
</header>

<div class="kpis">
  <div class="kpi"><b>{fmtn(n_total)}</b><span>Unterschriften gesamt</span></div>
  <div class="kpi"><b>{fmtn(max(hour_counts))}</b><span>Spitzenstunde ({peak_label})</span></div>
  <div class="kpi"><b>{fem_share:.0%}</b><span>Frauenanteil (geschätzt)</span></div>
  <div class="kpi"><b>{fach:.0%}</b><span>Psych-, Gesundheits- &amp; Sozialberufe</span></div>
  <div class="kpi"><b>{kreis_cov:.0%}</b><span>einem Kreis zuordenbar (400 Kreise)</span></div>
  <div class="kpi"><b>{r2:.0%}</b><span>der Kreis-Varianz statistisch erklärbar</span></div>
</div>

<div class="insights">
  <strong>Kernaussagen</strong>
  <ul>
    <li><b>Die Petition gewann über zwei Tage an Fahrt statt abzuflachen:</b> nur {first24:.0%} kamen in den ersten 24&nbsp;Stunden; der stärkste Tag war Tag&nbsp;3 ({fmtn(day_counts.max())} am {day_peak}). Der Export endet Fr&nbsp;früh — das Ende der Welle ist nicht im Datensatz.</li>
    <li><b>Es ist eine Milieu-Karte, keine Bedarfs-Karte:</b> Unterschriften pro Kopf korrelieren stark mit dem Grünen-Anteil (ρ&nbsp;=&nbsp;{rho['share_Gruene']:+.2f}) und negativ mit dem AfD-Anteil (ρ&nbsp;=&nbsp;{rho['share_AfD']:+.2f}) — die sozioökonomische Lage des Kreises (GISD) erklärt dagegen fast nichts (ρ&nbsp;=&nbsp;{rho['gisd_score']:+.2f}).</li>
    <li><b>Der stärkste Einzelfaktor ist die Universität:</b> Kreise mit Psychologie-Studiengang mobilisieren im Median {fmtn(uni_med[True])} je 100k gegenüber {fmtn(uni_med[False])} in den übrigen Kreisen — Faktor&nbsp;{uni_med[True]/uni_med[False]:.1f}. Die Top-Liste (Münster, Freiburg, Würzburg, Heidelberg&nbsp;…) ist praktisch eine Liste von Uni-Städten.</li>
    <li><b>Der Osten ist gespalten, nicht abstinent:</b> Ost-Flächenkreise liegen im Median bei {fmtn(east_nouni)} je 100k (West-Fläche: {fmtn(west_nouni)}), aber Ost-Unistädte wie Leipzig und Jena erreichen {fmtn(east_uni)} — Berlin führt mit {fmtn(grp.loc['Berlin','per100k'])} alle Regionen an.</li>
    <li><b>Das AfD-Gefälle ist drastisch:</b> im Fünftel der Kreise mit dem höchsten AfD-Anteil kommen im Schnitt {fmtn(afd_hi)} Unterschriften je 100k zusammen, im Fünftel mit dem niedrigsten {fmtn(afd_lo)} — Faktor&nbsp;{afd_lo/afd_hi:.1f}.</li>
    <li>Die Unterzeichnenden bleiben überwiegend weiblich (~{fem_share:.0%}) und fachnah ({psych_share:.0%} Psychotherapie/Psychologie, {fach:.0%} inkl. Gesundheit &amp; Soziales); Studierende sind mit {stud_share:.0%} die größte Einzelgruppe.</li>
  </ul>
</div>

<h2>Zeitverlauf</h2>
<p>Stündliche Neueingänge und kumulierte Summe; Tagesrhythmus normalisiert auf das 60h-Fenster.</p>
<div class="grid">
  <div class="card wide"><h3>Unterschriften pro Stunde &amp; kumuliert</h3><p>lokale Zeit (Europe/Berlin)</p>
    <div class="chartbox"><canvas id="cTimeline"></canvas></div></div>
  <div class="card wide"><h3>Tagesrhythmus</h3><p>durchschnittliche Unterschriften je Tagesstunde</p>
    <div class="chartbox"><canvas id="cHod"></canvas></div></div>
</div>

<h2>Wer unterschreibt?</h2>
<p>Berufskategorien (regelbasiert), Geschlechter-Schätzung (Berufs-Sprachform + Vornamen-Votum), akademische Titel.</p>
<div class="grid">
  <div class="card wide"><h3>Berufskategorien</h3><p>alle {fmtn(n_total)} Angaben in 16 Gruppen</p>
    <div class="chartbox tall"><canvas id="cCats"></canvas></div></div>
  <div class="card"><h3>Geschlecht (Näherung)</h3><p>{fmtn(n_f+n_m)} zuordenbar, {fmtn(n_u)} unbestimmt</p>
    <div class="chartbox"><canvas id="cGender"></canvas></div></div>
  <div class="card"><h3>Häufigste akademische Titel</h3><p>{fmtn((df['academicTitle']!='').sum())} mit Titel-Angabe · {title_share:.1%} gesamt · {psych_title:.0%} in der Gruppe Psych.</p>
    <div class="chartbox"><canvas id="cTitles"></canvas></div></div>
  <div class="card wide"><h3>Häufigste Berufsangaben (roh)</h3><p>unbereinigt, wie angegeben</p>
    <div class="chartbox"><canvas id="cJobs"></canvas></div></div>
</div>

<h2>Geografie: Bundesländer</h2>
<p>Bundesland für {geo_cov:.0%} der Unterschriften bestimmbar (Ortsname bzw. PLZ, amtliche Referenzen).</p>
<div class="maps">
  <div class="card mapcard"><h3>Unterschriften gesamt</h3><p>absolut je Bundesland</p>{map_abs}</div>
  <div class="card mapcard"><h3>Je 100.000 Einwohner</h3><p>Mobilisierung pro Kopf</p>{map_rel}</div>
  <div class="card"><h3>Ranking je 100k</h3><p>absolut &amp; pro Kopf</p><table>{state_table}</table></div>
</div>
<div class="grid" style="margin-top:18px">
  <div class="card wide"><h3>Top-15 Städte</h3><p>nach absoluter Zahl</p>
    <div class="chartbox"><canvas id="cCities"></canvas></div></div>
</div>

<h2>Kreisebene: Was erklärt die Mobilisierung?</h2>
<p>{kreis_cov:.0%} der Unterschriften sind einem der 400 Kreise zuordenbar. Vergleichsdaten:
Bundestagswahl 2025 (Zweitstimmen, bevölkerungsgewichtet von Wahlkreisen auf Kreise umgelegt),
RKI-Deprivationsindex GISD (2023), Bevölkerungsdichte (Destatis GV100).
Jeder Punkt in den Streudiagrammen ist ein Kreis.</p>

<div class="maps">
  <div class="card mapcard" style="grid-column:span 2"><h3>Unterschriften je 100k — alle 400 Kreise</h3>
    <p>Farbskala nach Perzentil (hell = wenige, dunkel = viele); Tooltip zeigt Werte</p>{map_kreise}</div>
  <div class="card"><h3>Top-15 Kreise je 100k</h3><p>fast ausnahmslos Uni-Städte</p><table>{top15_rows}</table></div>
</div>

<div class="legend" style="margin-top:14px">
  <span><i style="background:#3d5a80"></i>West</span>
  <span><i style="background:#c2371f"></i>Ost</span>
  <span><i style="background:#171512"></i>Berlin</span>
  <span>· y-Achse logarithmisch: Unterschriften je 100k</span>
</div>
<div class="grid">
  <div class="card"><h3>AfD-Zweitstimmenanteil</h3><p>ρ = {rho['share_AfD']:+.2f} — je stärker AfD, desto weniger Unterschriften</p>
    <div class="chartbox"><canvas id="scAfD"></canvas></div></div>
  <div class="card"><h3>Grünen-Zweitstimmenanteil</h3><p>ρ = {rho['share_Gruene']:+.2f} — das Grünen-Milieu unterschreibt</p>
    <div class="chartbox"><canvas id="scGruene"></canvas></div></div>
  <div class="card"><h3>Sozioökonomische Deprivation (GISD)</h3><p>ρ = {rho['gisd_score']:+.2f} — Wohlstand erklärt kaum etwas</p>
    <div class="chartbox"><canvas id="scGisd"></canvas></div></div>
  <div class="card"><h3>Bevölkerungsdichte (log)</h3><p>ρ = {rho['log_density']:+.2f} — Urbanität ist der Grundtreiber</p>
    <div class="chartbox"><canvas id="scDens"></canvas></div></div>
  <div class="card"><h3>Ost / West / Berlin</h3><p>je 100k, aufgeteilt in Psych-Berufe vs. übrige</p>
    <div class="chartbox"><canvas id="cOstWest"></canvas></div></div>
  <div class="card"><h3>Universitätseffekt</h3><p>Median je 100k — Kreise mit/ohne Psychologie-Studiengang</p>
    <div class="chartbox"><canvas id="cUni"></canvas></div></div>
</div>

<div class="insights" style="margin-top:18px">
  <strong>Gemeinsames Modell (standardisierte Regression, R² = {r2:.2f})</strong>
  <ul>
    <li>Hält man alle Faktoren gleichzeitig konstant, bleiben <b>AfD-Anteil (β&nbsp;=&nbsp;{betas['share_AfD']:+.2f})</b>, <b>Dichte (β&nbsp;=&nbsp;{betas['log_density']:+.2f})</b> und <b>Grünen-Anteil (β&nbsp;=&nbsp;{betas['share_Gruene']:+.2f})</b> die tragenden Erklärungen; Deprivation trägt fast nichts bei (β&nbsp;=&nbsp;{betas['gisd_score']:+.2f}).</li>
    <li>Der Ost-Koeffizient dreht im Modell ins Positive (β&nbsp;=&nbsp;{betas['east']:+.2f}): das niedrige Ost-Niveau geht statistisch im AfD-Anteil auf. <b>Bei gleichem politischen Milieu unterschreibt der Osten nicht weniger</b> — Leipzig, Jena und Dresden zeigen das konkret.</li>
    <li>Interpretation mit Vorsicht: ökologische Korrelationen auf Kreisebene, keine Aussagen über Individuen.</li>
  </ul>
</div>

<footer>
  <b>Methodik &amp; Grenzen:</b> Kreiszuordnung über amtliche Ortsnamen (GV100, bevölkerungsgewichtet bei Namensgleichheit) bzw. PLZ (GeoNames); {1-kreis_cov:.0%} bleiben unzuordenbar.
  Wahlergebnisse: Zweitstimmen BTW 23.02.2025 (Bundeswahlleiterin), von Wahlkreisen bevölkerungsgewichtet auf Kreise umgelegt (Summe stimmt exakt mit dem amtlichen Ergebnis überein).
  GISD: RKI, Kreisebene 2023 (CC-BY 4.0). Bevölkerung/Fläche: Destatis GV100 (31.12.2024).
  Geschlecht ist eine sprachbasierte Schätzung, keine Selbstauskunft. Berufskategorien regelbasiert ({(cat_counts.get('Sonstige',0)+cat_counts.get('Unbekannt',0))/n_total:.0%} Sonstige/Unbekannt).
  Uni-Kennzeichnung: ~56 Kreise mit Psychologie-Studiengang (approximative Liste).
  Psychotherapeuten-Dichte je Kreis (KBV) ist nicht frei maschinenlesbar verfügbar — bekannte Lücke.
  Rohdaten &amp; Quellen: <code>external/README.md</code>. Erstellt {pd.Timestamp.now().strftime('%d.%m.%Y')}.
</footer>
</div>

<script>
const D = {json.dumps(payload, ensure_ascii=False)};
const INK = "#171512", MUTED = "#7a7468", ACC = "#c2371f", LINE = "#e6e1d6";
Chart.defaults.color = MUTED; Chart.defaults.borderColor = LINE;
Chart.defaults.font.family = '-apple-system, "Helvetica Neue", Segoe UI, sans-serif';
const nf = new Intl.NumberFormat('de-DE');

new Chart(cTimeline, {{ data: {{ labels: D.hourLabels, datasets: [
  {{ type:'bar', label:'pro Stunde', data:D.hourCounts, backgroundColor:'#c2371f99', yAxisID:'y' }},
  {{ type:'line', label:'kumuliert', data:D.cumCounts, borderColor:INK, borderWidth:1.5,
     pointRadius:0, yAxisID:'y2', tension:.2 }} ] }},
  options: {{ maintainAspectRatio:false, interaction:{{mode:'index',intersect:false}},
    scales: {{ x:{{ ticks:{{ maxTicksLimit:14 }}, grid:{{display:false}} }},
      y:{{ position:'left', ticks:{{callback:v=>nf.format(v)}} }},
      y2:{{ position:'right', grid:{{display:false}}, ticks:{{callback:v=>nf.format(v)}} }} }},
    plugins:{{ legend:{{position:'top',align:'end'}} }} }} }});

new Chart(cHod, {{ type:'bar', data: {{ labels:[...Array(24).keys()].map(h=>h+' Uhr'),
  datasets:[{{ data:D.hod, backgroundColor:D.hod.map((v,i)=> i<6 ? '#17151266' : '#c2371fcc') }}] }},
  options: {{ maintainAspectRatio:false, plugins:{{legend:{{display:false}}}},
    scales:{{ x:{{grid:{{display:false}}, ticks:{{maxTicksLimit:12}}}}, y:{{ticks:{{callback:v=>nf.format(v)}}}} }} }} }});

const hbar = (el, labels, data, color=ACC) => new Chart(el, {{ type:'bar',
  data:{{ labels, datasets:[{{ data, backgroundColor:color }}] }},
  options:{{ indexAxis:'y', maintainAspectRatio:false, plugins:{{legend:{{display:false}}}},
    scales:{{ x:{{ticks:{{callback:v=>nf.format(v)}}}}, y:{{grid:{{display:false}}}} }} }} }});
hbar(cCats, D.catLabels, D.catCounts);
hbar(cTitles, D.titleLabels, D.titleCounts, '#17151299');
hbar(cJobs, D.jobLabels, D.jobCounts, '#8a6d3bcc');
hbar(cCities, D.cityLabels, D.cityCounts, '#3d5a80cc');

new Chart(cGender, {{ type:'doughnut', data:{{ labels:D.genderLabels,
  datasets:[{{ data:D.genderCounts, backgroundColor:[ACC,'#171512','#d8d2c4'], borderColor:'#fff' }}] }},
  options:{{ maintainAspectRatio:false, cutout:'62%', plugins:{{ legend:{{position:'bottom'}} }} }} }});

// --- kreis scatters ---
const scatter = (el, pts, xLabel, logX=false) => new Chart(el, {{ type:'scatter',
  data:{{ datasets:[{{ data:pts, pointRadius:2.5, pointHoverRadius:5,
    backgroundColor: pts.map(p=>D.groupColor[p.g] + 'bb') }}] }},
  options:{{ maintainAspectRatio:false, plugins:{{ legend:{{display:false}},
      tooltip:{{ callbacks:{{ label: c => `${{c.raw.n}}: ${{nf.format(c.raw.y)}} je 100k (x=${{nf.format(c.raw.x)}})` }} }} }},
    scales:{{ x:{{ type: logX?'logarithmic':'linear', title:{{display:true, text:xLabel, font:{{size:11}}}} }},
      y:{{ type:'logarithmic', ticks:{{callback:v=>[30,100,300,1000,3000].includes(v)?nf.format(v):null}} }} }} }} }});
scatter(scAfD, D.scAfD, 'AfD-Zweitstimmen %');
scatter(scGruene, D.scGruene, 'Grüne-Zweitstimmen %');
scatter(scGisd, D.scGisd, 'GISD-Score (höher = deprivierter)');
scatter(scDens, D.scDens, 'Einwohner je km²', true);

new Chart(cOstWest, {{ type:'bar', data:{{ labels:D.owLabels, datasets:[
    {{ label:'Psych-Berufe', data:D.owPsych, backgroundColor:'#171512cc' }},
    {{ label:'übrige', data:D.owNon, backgroundColor:'#c2371fcc' }} ] }},
  options:{{ maintainAspectRatio:false, scales:{{ x:{{stacked:true, grid:{{display:false}}}},
    y:{{stacked:true, ticks:{{callback:v=>nf.format(v)}}}} }},
    plugins:{{ legend:{{position:'bottom'}} }} }} }});

new Chart(cUni, {{ type:'bar', data:{{ labels:D.uniLabels,
    datasets:[{{ data:D.uniMed, backgroundColor:['#3d5a80cc','#d8d2c4'] }}] }},
  options:{{ indexAxis:'y', maintainAspectRatio:false, plugins:{{legend:{{display:false}}}},
    scales:{{ x:{{ticks:{{callback:v=>nf.format(v)}}}}, y:{{grid:{{display:false}}}} }} }} }});
</script>
</body></html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("written:", OUT, f"{len(html)/1024:.0f} KB")
print("kreis cov:", f"{kreis_cov:.1%}", "| state cov:", f"{geo_cov:.1%}",
      "| R²:", round(r2, 3), "| rho:", {k: round(v, 2) for k, v in rho.items()})
