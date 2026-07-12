# External reference data — fetched 2026-07-11

Raw sources used to enrich `Uschriften_clean.csv` and build `kreis_stats.csv`.
All joins run on the 5-digit Kreis code (AGS) unless noted.

| File | Source | License / Notes |
|---|---|---|
| `btw25_kerg2.csv` | Bundeswahlleiterin, Bundestagswahl 23.02.2025, endgültiges Ergebnis je Wahlkreis. https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata.html | DL-DE BY 2.0 |
| `btw25_wkr_gemeinden.csv` | Bundeswahlleiterin: Zuordnung Gemeinden → Wahlkreise (Gebietsstand 30.11.2024) | DL-DE BY 2.0 |
| `btw25_strukturdaten.csv` | Bundeswahlleiterin: Strukturdaten je Wahlkreis (unused so far, kept for reference) | DL-DE BY 2.0 |
| `GISD_Bund.tsv` | Robert Koch-Institut, German Index of Socioeconomic Deprivation. github.com/robert-koch-institut/German_Index_of_Socioeconomic_Deprivation_GISD | CC-BY 4.0; used level `Kreis`, year 2023 |
| `gemeindeverzeichnis_gv100.xlsx` | Destatis Gemeindeverzeichnis (GV100), Gebietsstand 31.12.2025, Bevölkerung 31.12.2024 | © Destatis, dl-de/by-2-0; Gemeinde-Einwohner & Flächen |
| `kreise_geo.geojson` | opendatasoft `georef-germany-kreis` (400 Kreise, krs_code = AGS) | ODbL-ish public dataset |
| `bundeslaender_geo.geojson` | github.com/isellsoap/deutschlandGeoJSON (2_bundeslaender, niedrig) | GeoBasis-DE / BKG, dl-de/by-2-0 |
| `geonames_plz_DE.txt` | GeoNames postal codes DE (download.geonames.org/export/zip/DE.zip) | CC-BY 4.0; PLZ→Ort/Kreis (admin3 = AGS) |

## Election apportionment method
Wahlkreis results (Zweitstimmen) are apportioned to Kreise via population weights:
each Wahlkreis's votes are split across the Kreise of its member Gemeinden,
weighted by Gemeinde population (GV100). Gemeinden split across several
Wahlkreise (large cities) have their population divided equally among those
Wahlkreise — harmless at Kreis level since the parts share the same Kreis.
Apportioned valid-vote total reconciles exactly with the official count
(49,649,512).

## Known gap
Psychotherapist density per Kreis (KBV Bundesarztregister / Bedarfsplanung)
is only published behind interactive portals (gesundheitsdaten.kbv.de,
versorgungsatlas.de) — no programmatic download found. The report uses the
internal measure "psych-professional signatures per 100k" instead.
