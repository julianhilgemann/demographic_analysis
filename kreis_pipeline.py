# -*- coding: utf-8 -*-
"""Kreis-level enrichment + analysis for Uschriften_clean.csv.

Outputs:
  - Uschriften_clean.csv gains: bundesland, kreis_ags, kreis_name, ost_west, geschlecht_geschaetzt
  - psytition/kreis_stats.csv: per-Kreis master table (signatures, politics, GISD, density ...)
  - psytition/external/: raw fetched sources + README
  - printed analysis (correlations, OLS, group stats)
"""
import pandas as pd
import numpy as np
import re
import json
import shutil
import unicodedata
from collections import Counter, defaultdict

SCRATCH = "/private/tmp/claude-501/-Users-admin-Desktop-hyperadapted/68cc7daa-4deb-45a3-b7b0-dab25a8802db/scratchpad"
PSY = "/Users/admin/Desktop/psytition"
MAIN = f"{PSY}/Uschriften_clean.csv"

# ================================================================ helpers
def norm_city(s):
    s = unicodedata.normalize("NFC", str(s)).lower().strip()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

# ================================================================ 1. GeoNames -> Kreis maps
gn = pd.read_csv(f"{SCRATCH}/DE.txt", sep="\t", header=None, dtype=str,
                 names=["cc", "plz", "place", "state", "s1", "a2", "c2", "a3", "c3", "lat", "lon", "acc"])
gn = gn[gn["c3"].notna() & gn["c3"].str.fullmatch(r"\d{5}")]

plz2ags, plz2state = {}, {}
for plz, ags, st in zip(gn["plz"], gn["c3"], gn["state"]):
    plz2ags.setdefault(plz, ags)
    plz2state.setdefault(plz, st)

city_ags_counts, city_state_counts = defaultdict(Counter), defaultdict(Counter)
for place, ags, st in zip(gn["place"], gn["c3"], gn["state"]):
    n = norm_city(place)
    city_ags_counts[n][ags] += 1
    city_state_counts[n][st] += 1
city2ags = {}
for c, cnt in city_ags_counts.items():
    ags, n = cnt.most_common(1)[0]
    if n / sum(cnt.values()) >= 0.75:
        city2ags[c] = ags
city2state = {}
for c, cnt in city_state_counts.items():
    st, n = cnt.most_common(1)[0]
    if n / sum(cnt.values()) >= 0.75:
        city2state[c] = st

# ================================================================ 1b. GV100 city->Kreis (pop-weighted, with aliases)
gv_raw = pd.read_excel(f"{SCRATCH}/gv100.xlsx", sheet_name="Onlineprodukt_Gemeinden31122025",
                       header=None, dtype=str)
gv_raw = gv_raw[gv_raw[0] == "60"].copy()
gv_raw["ags5"] = gv_raw[2].str.zfill(2) + gv_raw[3].str.zfill(1) + gv_raw[4].str.zfill(2)
gv_raw["gpop"] = pd.to_numeric(gv_raw[9], errors="coerce").fillna(0)

QUALI = re.compile(r"^(.*?)\s+(in der|an der|am|ob der|vor der|bei|im|a\.\s?d\.\S*|i\.\s?d\.\S*|v\.\s?d\.\S*|b\.\s?\S+)\b.*$", re.I)
def gem_aliases(raw_name):
    base = raw_name.split(",")[0].strip()
    noparen = re.sub(r"\s*\([^)]*\)", "", base).strip()
    out = {norm_city(base), norm_city(noparen)}
    m = QUALI.match(noparen)
    if m:
        out.add(norm_city(m.group(1)))
    return {a for a in out if a}

alias_pop = defaultdict(Counter)
for name, ags5, gp in zip(gv_raw[7], gv_raw["ags5"], gv_raw["gpop"]):
    for a in gem_aliases(str(name)):
        alias_pop[a][ags5] += gp
gv_city2ags = {}
for a, cnt in alias_pop.items():
    ags, p = cnt.most_common(1)[0]
    if sum(cnt.values()) > 0 and p / sum(cnt.values()) >= 0.75:
        gv_city2ags[a] = ags

STATE_BY_CODE = {"01": "Schleswig-Holstein", "02": "Hamburg", "03": "Niedersachsen",
                 "04": "Bremen", "05": "Nordrhein-Westfalen", "06": "Hessen",
                 "07": "Rheinland-Pfalz", "08": "Baden-Württemberg", "09": "Bayern",
                 "10": "Saarland", "11": "Berlin", "12": "Brandenburg",
                 "13": "Mecklenburg-Vorpommern", "14": "Sachsen", "15": "Sachsen-Anhalt",
                 "16": "Thüringen"}

# ================================================================ 2. load + enrich main CSV
df = pd.read_csv(MAIN, dtype=str).fillna("")

def resolve_ags(plz, ort):
    # city name first (exact Gemeinde->Kreis when unambiguous), PLZ as fallback
    # (rural PLZ areas can straddle Kreis borders)
    n = norm_city(ort)
    hit = gv_city2ags.get(n)
    if hit:
        return hit
    if plz and plz in plz2ags:
        return plz2ags[plz]
    return city2ags.get(n, "")

df["kreis_ags"] = [resolve_ags(p, o) for p, o in zip(df["plz"], df["ort"])]
df["bundesland"] = [STATE_BY_CODE.get(a[:2], "") if a else city2state.get(norm_city(o), "")
                    for a, o in zip(df["kreis_ags"], df["ort"])]

EAST = {"12", "13", "14", "15", "16"}
def ost_west(ags):
    if not ags:
        return ""
    if ags[:2] == "11":
        return "Berlin"
    return "Ost" if ags[:2] in EAST else "West"
df["ost_west"] = df["kreis_ags"].map(ost_west)

# ---- gender estimate (same method as report: job-form seed -> first-name vote)
FEM_EX = ("admin", "medizin", "termin", "benjamin", "quereinstieg")
def occ_gender(s):
    s = s.lower().strip().rstrip(".")
    if not s:
        return ""
    w = re.split(r"[\s/|,(]+", s)[0]
    if w.endswith(FEM_EX):
        return ""
    if w.endswith(("in", "frau", "schwester", "hebamme", "mutter", "mama", "angestellte", "beauftragte", "witwe", "ärztin")):
        return "f"
    if w.endswith(("er", "eur", "or", "arzt", "mann", "ent", "ant", "ist", "oge", "koch", "vater", "papa", "ling")):
        return "m"
    return ""

occ_g = df["berufsbezeichnung"].map(occ_gender)
first_tok = df["firstName"].str.split().str[0].str.lower().fillna("")
votes = defaultdict(Counter)
for name, g in zip(first_tok, occ_g):
    if g and name:
        votes[name][g] += 1
name2g = {}
for name, cnt in votes.items():
    total = sum(cnt.values())
    g, n = cnt.most_common(1)[0]
    if total >= 5 and n / total >= 0.85:
        name2g[name] = g
df["geschlecht_geschaetzt"] = [name2g.get(nm, og) for nm, og in zip(first_tok, occ_g)]

print("kreis coverage:", (df["kreis_ags"] != "").mean().round(4))
print("ost_west:", df["ost_west"].value_counts().to_dict())

# ================================================================ 3. GV100: Gemeinde pop, Kreis pop/area
gv = pd.read_excel(f"{SCRATCH}/gv100.xlsx", sheet_name="Onlineprodukt_Gemeinden31122025",
                   header=None, dtype=str)
gv = gv[gv[0] == "60"].copy()
gv["gkey"] = (gv[2].str.zfill(2) + gv[3].str.zfill(1) + gv[4].str.zfill(2)
              + gv[6].str.zfill(3))  # Land+RB+Kreis+Gem — unique without Verband
gv["ags5"] = gv["gkey"].str[:5]
gv["pop"] = pd.to_numeric(gv[9], errors="coerce").fillna(0)
gv["area"] = pd.to_numeric(gv[8], errors="coerce").fillna(0)
gem_pop = dict(zip(gv["gkey"], gv["pop"]))
kreis_pop = gv.groupby("ags5")["pop"].sum()
kreis_area = gv.groupby("ags5")["area"].sum()
print("gemeinden:", len(gv), "| kreise:", kreis_pop.size, "| pop total:", int(kreis_pop.sum()))

# ================================================================ 4. election: WK results -> Kreis
kerg = pd.read_csv(f"{SCRATCH}/btw25_kerg2.csv", sep=";", skiprows=9, dtype=str, encoding="utf-8-sig")
wk = kerg[(kerg["Gebietsart"] == "Wahlkreis")].copy()
wk["Anzahl"] = pd.to_numeric(wk["Anzahl"], errors="coerce").fillna(0)
PARTIES = {"CDU": "Union", "CSU": "Union", "SPD": "SPD", "GRÜNE": "Gruene",
           "AfD": "AfD", "Die Linke": "Linke", "FDP": "FDP", "BSW": "BSW"}
pv = wk[(wk["Gruppenart"] == "Partei") & (wk["Stimme"] == "2") & wk["Gruppenname"].isin(PARTIES)].copy()
pv["party"] = pv["Gruppenname"].map(PARTIES)
wk_votes = pv.pivot_table(index="Gebietsnummer", columns="party", values="Anzahl", aggfunc="sum").fillna(0)
valid = wk[(wk["Gruppenart"] == "System-Gruppe") & (wk["Gruppenname"] == "Gültige") & (wk["Stimme"] == "2")]
wk_valid = dict(zip(valid["Gebietsnummer"], valid["Anzahl"]))

zu = pd.read_csv(f"{SCRATCH}/btw25_wkr_gemeinden.csv", sep=";", comment="#", dtype=str)
zu = zu[zu["RGS_Gemeinde"].notna()].copy()
zu["gkey"] = (zu["RGS_Land"].str.zfill(2) + zu["RGS_RegBez"].str.zfill(1)
              + zu["RGS_Kreis"].str.zfill(2) + zu["RGS_Gemeinde"].str.zfill(3))
zu["wknr"] = zu["Wahlkreis-Nr"]
zu = zu.drop_duplicates(["gkey", "wknr"])
n_wk_per_gem = zu.groupby("gkey")["wknr"].nunique()
zu["gpop"] = zu["gkey"].map(gem_pop).fillna(0) / zu["gkey"].map(n_wk_per_gem).fillna(1)
zu["ags5"] = zu["gkey"].str[:5]
print("gemeinde join hit rate:", zu["gkey"].isin(gem_pop).mean().round(4))

# weights: share of WK population belonging to each Kreis
wk_pop = zu.groupby("wknr")["gpop"].sum()
kreis_votes = defaultdict(lambda: defaultdict(float))
kreis_valid = defaultdict(float)
for (wknr, ags5), grp in zu.groupby(["wknr", "ags5"]):
    if wknr not in wk_votes.index or wk_pop.get(wknr, 0) == 0:
        continue
    w = grp["gpop"].sum() / wk_pop[wknr]
    for party in wk_votes.columns:
        kreis_votes[ags5][party] += wk_votes.loc[wknr, party] * w
    kreis_valid[ags5] += float(wk_valid.get(wknr, 0)) * w

pol = pd.DataFrame(kreis_votes).T
pol["valid2"] = pd.Series(kreis_valid)
for p in wk_votes.columns:
    pol[f"share_{p}"] = pol[p] / pol["valid2"] * 100
print("kreise with politics:", len(pol), "| apportioned valid votes:",
      int(pol['valid2'].sum()), "vs official:", int(sum(float(v) for v in wk_valid.values())))

# ================================================================ 5. GISD (Kreis, 2023)
gisd = pd.read_csv(f"{SCRATCH}/GISD_Bund.tsv", sep="\t", dtype=str)
gisd = gisd[(gisd["region_type"] == "Kreis") & (gisd["year"] == "2023")].copy()
gisd["gisd_score"] = pd.to_numeric(gisd["gisd_score"])
gisd["gisd_5"] = pd.to_numeric(gisd["gisd_5"])
gisd = gisd.set_index("region_id")[["region_name", "gisd_score", "gisd_5"]]

# ================================================================ 6. per-Kreis signature metrics
sig = df[df["kreis_ags"] != ""].groupby("kreis_ags").agg(
    signatures=("id", "size"),
    sig_psych=("berufskategorie", lambda s: (s == "Psychotherapie & Psychologie").sum()),
    sig_stud=("berufskategorie", lambda s: (s == "Student:in").sum()),
    sig_med=("berufskategorie", lambda s: s.isin(["Medizin & Pflege", "Gesundheitswesen (sonstige)"]).sum()),
    fem=("geschlecht_geschaetzt", lambda s: (s == "f").sum()),
    gender_known=("geschlecht_geschaetzt", lambda s: (s != "").sum()),
)

K = pd.DataFrame(index=sorted(kreis_pop.index))
K["kreis_name"] = gisd["region_name"]
K["pop"] = kreis_pop
K["area_km2"] = kreis_area
K["density"] = K["pop"] / K["area_km2"]
K["ost_west"] = [ost_west(a) for a in K.index]
K["bundesland_code"] = [a[:2] for a in K.index]
K = K.join(sig).join(gisd[["gisd_score", "gisd_5"]])
K = K.join(pol[[c for c in pol.columns if str(c).startswith("share_")]])
for c in ["signatures", "sig_psych", "sig_stud", "sig_med", "fem", "gender_known"]:
    K[c] = K[c].fillna(0).astype(int)
K["per100k"] = K["signatures"] / K["pop"] * 1e5
K["psych_per100k"] = K["sig_psych"] / K["pop"] * 1e5
K["nonpsych_per100k"] = (K["signatures"] - K["sig_psych"]) / K["pop"] * 1e5
K["fem_share"] = np.where(K["gender_known"] > 0, K["fem"] / K["gender_known"], np.nan)

# psychology-programme university Kreise (approximate list of cities)
UNI_PSY = ["Berlin", "Hamburg", "München", "Köln", "Bonn", "Aachen", "Münster", "Bochum",
           "Bielefeld", "Duisburg", "Essen", "Wuppertal", "Siegen", "Hagen", "Düsseldorf",
           "Marburg", "Gießen", "Frankfurt am Main", "Darmstadt", "Kassel", "Mainz",
           "Landau in der Pfalz", "Trier", "Koblenz", "Saarbrücken", "Heidelberg", "Mannheim",
           "Tübingen", "Freiburg im Breisgau", "Konstanz", "Ulm", "Würzburg", "Bamberg",
           "Erlangen", "Regensburg", "Eichstätt", "Jena", "Erfurt", "Leipzig", "Dresden",
           "Chemnitz", "Halle (Saale)", "Magdeburg", "Greifswald", "Rostock", "Kiel", "Lübeck",
           "Hannover", "Braunschweig", "Osnabrück", "Oldenburg", "Göttingen", "Hildesheim",
           "Bremen", "Potsdam", "Witten", "Bremerhaven"]
uni_ags = {gv_city2ags.get(norm_city(c)) or city2ags.get(norm_city(c)) for c in UNI_PSY} - {None}
K["uni_psych"] = [a in uni_ags for a in K.index]

K.index.name = "kreis_ags"
K.round(4).to_csv(f"{PSY}/kreis_stats.csv")
print("\nkreis_stats.csv written:", K.shape)

# ================================================================ 7. save main CSV + externals
df.to_csv(MAIN, index=False, encoding="utf-8")
print("main CSV updated:", df.shape, "cols:", list(df.columns))

import os
os.makedirs(f"{PSY}/external", exist_ok=True)
for src, dst in [
    ("btw25_kerg2.csv", "btw25_kerg2.csv"),
    ("btw25_wkr_gemeinden.csv", "btw25_wkr_gemeinden.csv"),
    ("btw25_strukturdaten.csv", "btw25_strukturdaten.csv"),
    ("GISD_Bund.tsv", "GISD_Bund.tsv"),
    ("gv100.xlsx", "gemeindeverzeichnis_gv100.xlsx"),
    ("georef_kreise.geojson", "kreise_geo.geojson"),
    ("bundeslaender.geojson", "bundeslaender_geo.geojson"),
    ("DE.txt", "geonames_plz_DE.txt"),
]:
    shutil.copy(f"{SCRATCH}/{src}", f"{PSY}/external/{dst}")
print("externals saved")

# ================================================================ 8. analysis
A = K.dropna(subset=["gisd_score", "share_Gruene"]).copy()
A = A[A["per100k"] > 0]
A["log_density"] = np.log10(A["density"])
A["east"] = (A["ost_west"] == "Ost").astype(float)

print("\n=== Spearman correlations with signatures per 100k (n=%d Kreise) ===" % len(A))
for c in ["share_Gruene", "share_Linke", "share_AfD", "share_Union", "share_SPD",
          "share_FDP", "share_BSW", "gisd_score", "log_density"]:
    r = A["per100k"].corr(A[c], method="spearman")
    print(f"  {c:15} rho = {r:+.3f}")

print("\n=== group means: signatures per 100k ===")
print(K.groupby("ost_west")[["per100k", "psych_per100k", "nonpsych_per100k"]].mean().round(1).to_string())
print("\nuni_psych:", K.groupby("uni_psych")["per100k"].agg(["mean", "median", "count"]).round(1).to_string())

# standardized OLS: what survives jointly?
X_cols = ["share_Gruene", "share_AfD", "gisd_score", "log_density", "east"]
Xz = (A[X_cols] - A[X_cols].mean()) / A[X_cols].std()
yz = (np.log10(A["per100k"]) - np.log10(A["per100k"]).mean()) / np.log10(A["per100k"]).std()
Xm = np.column_stack([np.ones(len(A)), Xz.values])
beta, res, *_ = np.linalg.lstsq(Xm, yz.values, rcond=None)
yhat = Xm @ beta
r2 = 1 - ((yz.values - yhat) ** 2).sum() / ((yz.values - yz.values.mean()) ** 2).sum()
print("\n=== standardized OLS on log10(per100k), R² = %.3f ===" % r2)
for name, b in zip(["intercept"] + X_cols, beta):
    print(f"  {name:15} beta = {b:+.3f}")

print("\n=== top 12 Kreise per 100k ===")
top = K.nlargest(12, "per100k")[["kreis_name", "per100k", "ost_west", "uni_psych"]]
print(top.round(0).to_string())
print("\n=== bottom 8 ===")
print(K.nsmallest(8, "per100k")[["kreis_name", "per100k", "ost_west"]].round(0).to_string())
