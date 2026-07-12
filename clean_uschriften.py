# -*- coding: utf-8 -*-
"""Cleaning pipeline for Uschriften.csv (German petition signatures)."""
import pandas as pd
import re
import sys
import unicodedata

SRC = "/Users/admin/Desktop/psytition/Uschriften.csv"
OUT = "/Users/admin/Desktop/psytition/Uschriften_clean.csv"
PLZ_REF = "/private/tmp/claude-501/-Users-admin-Desktop-hyperadapted/68cc7daa-4deb-45a3-b7b0-dab25a8802db/scratchpad/DE.txt"

WRITE = "--write" in sys.argv

# ---------------------------------------------------------------- reference
ref = pd.read_csv(PLZ_REF, sep="\t", header=None, dtype=str,
                  names=["cc", "plz", "place", "state", "s1", "a2", "c2", "a3", "c3", "lat", "lon", "acc"])
corporate = ref["place"].str.contains(r"GmbH|AG$| AG |KG$| KG |e\.V\.|Versicherung|Bank|Verlag|GmbH & Co", regex=True, na=False)
ref = ref[~corporate]

def norm_city(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower().strip()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s

# plz -> canonical place (first entry wins; GeoNames lists main locality first)
plz2city = {}
for plz, place in zip(ref["plz"], ref["place"]):
    plz2city.setdefault(plz, place)

# normalized city -> set of PLZs; fill only when unambiguous (exactly 1 PLZ)
city2plzs = {}
for plz, place in zip(ref["plz"], ref["place"]):
    city2plzs.setdefault(norm_city(place), set()).add(plz)
city2plz = {c: next(iter(p)) for c, p in city2plzs.items() if len(p) == 1}
known_cities = set(city2plzs.keys())

# ---------------------------------------------------------------- load
df = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig")
for c in df.columns:
    df[c] = df[c].str.strip()

# ---------------------------------------------------------------- ort / plz
SMALL_WORDS = {"am", "an", "der", "die", "das", "im", "in", "bei", "auf", "ob",
               "vor", "unter", "zu", "zur", "zum", "und", "den", "dem", "of", "the"}

def fix_case(city: str) -> str:
    if not city:
        return city
    # only re-case if all-lower or all-upper; otherwise trust the writer
    if city != city.lower() and city != city.upper():
        return city
    words = re.split(r"(\s+|-|\.|/)", city.lower())
    out, first = [], True
    for w in words:
        if re.fullmatch(r"\s+|-|\.|/", w) or w == "":
            out.append(w)
            continue
        if not first and w in SMALL_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
        first = False
    return "".join(out)

DATE_RE = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}\b")
JUNK_ORT = re.compile(r"^[-.,/?!*+\s]*$|^(k\.?\s?a\.?|keine angabe|xxx+|test)$", re.I)

def parse_ort(raw):
    """returns (plz, city)"""
    if not isinstance(raw, str) or not raw.strip():
        return "", ""
    s = DATE_RE.sub("", raw).strip(" ,;:.-")
    if JUNK_ORT.fullmatch(s):
        return "", ""
    plz, city = "", s
    m5 = re.search(r"\b(\d{5})\b", s)
    if m5:
        plz = m5.group(1)
        after = s[m5.end():].strip(" ,;:.-")
        before = s[:m5.start()].strip(" ,;:.-")
        city = after if after else before
    elif re.fullmatch(r"\d{5}\S+", s.split()[0]) and re.match(r"^\d{5}", s):
        plz, city = s[:5], s[5:].strip(" ,;:.-")
    else:
        m4 = re.fullmatch(r"(\d{4})", s) or re.match(r"^(\d{4})\s+(.+)$", s) or re.match(r"^(.+?)[,\s]+(\d{4})$", s)
        if m4:
            g = m4.groups()
            cand = ("0" + g[0]) if g[0].isdigit() else ("0" + g[-1])
            rest = (g[1] if len(g) > 1 and g[1] and not g[1].isdigit() else
                    (g[0] if not g[0].isdigit() else ""))
            if cand in plz2city:
                plz, city = cand, rest.strip(" ,;:.-")
        elif s.isdigit():
            return "", ""  # 2-3 digit junk
    # glued "22869Schenefeld"
    if not plz:
        mg = re.match(r"^(\d{5})(\D.*)$", s)
        if mg:
            plz, city = mg.group(1), mg.group(2).strip(" ,;:.-")
    # strip leftover digits/house numbers at edges of city
    city = re.sub(r"\b\d{1,4}[a-z]?\b", "", city).strip(" ,;:.-")
    city = re.sub(r"\s{2,}", " ", city)
    # multi-part "47057, Neudorf-Nord, Duisburg, NRW" -> pick part known in reference
    if "," in city:
        parts = [p.strip() for p in city.split(",") if p.strip()]
        known = [p for p in parts if norm_city(p) in known_cities]
        city = known[0] if known else (parts[0] if parts else "")
    # enrichment / validation against reference
    if plz and plz in plz2city:
        if not city or norm_city(city) not in known_cities:
            city = plz2city[plz]  # fixes "59379 Rentner", typos, districts
    elif plz and plz not in plz2city:
        plz = plz if re.fullmatch(r"\d{5}", plz) else ""
    if not plz and city:
        plz = city2plz.get(norm_city(city), "")
    return plz, fix_case(city)

parsed = df["ort"].map(parse_ort)
df["plz"] = [p for p, c in parsed]
df["ort_clean"] = [c for p, c in parsed]

# ---------------------------------------------------------------- academicTitle
def norm_key(s: str) -> str:
    return re.sub(r"[^a-zäöüß]+", "", s.lower())

TITLE_MAP = {
    "dr": "Dr.", "drin": "Dr.", "doktor": "Dr.", "doktorin": "Dr.",
    "drmed": "Dr. med.", "drmeddent": "Dr. med. dent.", "drmedvet": "Dr. med. vet.",
    "drphil": "Dr. phil.", "drrernat": "Dr. rer. nat.", "drrerpol": "Dr. rer. pol.",
    "drrermed": "Dr. rer. medic.", "drrermedic": "Dr. rer. medic.", "drrersoc": "Dr. rer. soc.",
    "dring": "Dr.-Ing.", "drjur": "Dr. jur.", "driur": "Dr. jur.", "drpaed": "Dr. paed.",
    "drsc": "Dr. sc.", "drscmed": "Dr. sc. med.", "drrercur": "Dr. rer. cur.",
    "drhabil": "Dr. habil.", "drdes": "Dr. des.", "drpü": "Dr. PH", "drph": "Dr. PH",
    "profdr": "Prof. Dr.", "prof": "Prof.", "professor": "Prof.", "professorin": "Prof.",
    "profdrmed": "Prof. Dr. med.", "profem": "Prof. em.", "apleprofdr": "apl. Prof. Dr.",
    "pddr": "PD Dr.", "pd": "PD", "privdozdr": "PD Dr.",
    "phd": "Ph.D.", "dphil": "Ph.D.", "md": "M.D.", "mdphd": "M.D. Ph.D.",
    "msc": "M.Sc.", "masterofscience": "M.Sc.", "mscpsych": "M.Sc.",
    "ma": "M.A.", "masterofarts": "M.A.", "maed": "M.Ed.", "masterofeducation": "M.Ed.",
    "meng": "M.Eng.", "mba": "MBA", "llm": "LL.M.", "llb": "LL.B.",
    "master": "Master", "masterabschluss": "Master", "mag": "Magister", "magister": "Magister",
    "magistra": "Magister", "magartium": "Magister", "magisterartium": "Magister",
    "bsc": "B.Sc.", "bachelorofscience": "B.Sc.", "ba": "B.A.", "bachelorofarts": "B.A.",
    "beng": "B.Eng.", "bed": "B.Ed.", "bachelorofeducation": "B.Ed.",
    "bachelor": "Bachelor", "bachelorabschluss": "Bachelor",
    "dipl": "Diplom", "diplom": "Diplom", "dip": "Diplom", "diplome": "Diplom",
    "diplpsych": "Dipl.-Psych.", "diplompsychologin": "Dipl.-Psych.", "diplompsychologe": "Dipl.-Psych.",
    "diplompsychologie": "Dipl.-Psych.", "diplpsychologin": "Dipl.-Psych.",
    "dipling": "Dipl.-Ing.", "diplingfh": "Dipl.-Ing. (FH)", "diplomingenieur": "Dipl.-Ing.",
    "diplomingenieurin": "Dipl.-Ing.",
    "diplpaed": "Dipl.-Päd.", "diplpäd": "Dipl.-Päd.", "diplompädagogin": "Dipl.-Päd.",
    "diplompädagoge": "Dipl.-Päd.", "diplompädagogik": "Dipl.-Päd.",
    "diplsozpäd": "Dipl.-Soz.Päd.", "diplsozialpädagogin": "Dipl.-Soz.Päd.",
    "diplomsozialpädagogin": "Dipl.-Soz.Päd.", "diplomsozialpädagoge": "Dipl.-Soz.Päd.",
    "diplsozarb": "Dipl.-Soz.Arb.", "diplomsozialarbeiterin": "Dipl.-Soz.Arb.",
    "diplkfm": "Dipl.-Kfm.", "diplkff": "Dipl.-Kff.", "diplkauffrau": "Dipl.-Kff.",
    "diplbetriebswirt": "Dipl.-Betriebswirt", "diplbetriebswirtin": "Dipl.-Betriebswirt",
    "diplsoz": "Dipl.-Soz.", "diplbiol": "Dipl.-Biol.", "diplphys": "Dipl.-Phys.",
    "staatsexamen": "Staatsexamen", "erstesstaatsexamen": "Staatsexamen",
    "zweitesstaatsexamen": "Staatsexamen", "staatsexamina": "Staatsexamen",
    "bacc": "Bachelor", "meister": "Meister", "meisterin": "Meister",
}
NO_TITLE = re.compile(r"^(-|—|–|\.|,|/|\*|\+|x+|xxx+|nein|keine[nr]?( titel)?|kein( titel)?|none|nichts|nix|no|na|n/?a|ohne( titel)?|entfällt|leider keiner?|frau|herr|fr|hr)$")

DEGREE_PAT = re.compile(
    r"dr|prof|phd|dphil|habil|master|magist|\bmag\b|msc|meng|maed|mba|llm|llb|"
    r"bachelor|bsc|beng|bed|\bba\b|\bma\b|dipl|staatsex|approbation|examen|md",
)

def clean_title(raw):
    """returns (clean_title, has_academic yes/no)"""
    if not isinstance(raw, str) or not raw.strip():
        return "", "no"
    s = raw.strip(" ,;")
    k = norm_key(s)
    if not k or NO_TITLE.fullmatch(s.lower().strip()):
        return "", "no"
    if k in TITLE_MAP:
        canon = TITLE_MAP[k]
        return canon, ("no" if canon == "Meister" else "yes")
    # combined titles like "Dr. med. M.Sc." or unseen variants: keyword check
    if DEGREE_PAT.search(k):
        return s, "yes"
    return s, "no"

tt = df["academicTitle"].map(clean_title)
df["academic_title_clean"] = [a for a, b in tt]
df["has_academic_title"] = [b for a, b in tt]

# ---------------------------------------------------------------- occupation
CATS = [
    ("Schüler:in / Ausbildung", r"sch(ü|u)ler|azubi|auszubilden|lehrling|abiturient|berufsschule|fsj|bufdi|freiwilligendienst|bfd\b|^ausbildung$"),
    ("Student:in", r"student|studier|studiu?m|stud\.|bachelorand|masterand|werkstudent"),
    ("Psychotherapie & Psychologie", r"psychother|psycholog|dipl\.?[- ]?psych|psychoanaly|kjp\b|kinder-?\s?und\s?jugendlichen(psycho)?therap|verhaltenstherap|\bpp\b|\bpia\b|psychodrama|gestalttherap|traumatherap|paartherap|familientherap|systemische?r? (therap|berat)|kinder- und jugendpsychiat|supervis"),
    ("Medizin & Pflege", r"arzt|ärzt|mediziner|psychiat|kranken(schwester|pfleg)|gesundheits- ?und ?kranken|pflegefach|pfleger(in)?$|altenpfleg|hebamme|entbindungspfleg|mfa\b|medizinische?r? fachangestellte|zahnmedizinische|apothek|pharmaz|pta\b|mta\b|mtla|mtra|laborant|notfallsanit|rettungssanit|rettungsassist|anästhes|chirurg|internist|kardiolog|onkolog|gynäkolog|urolog|radiolog|neurolog|dermatolog|orthopäd(e|in)|pädiater|allgemeinmedizin|zahnarzt|zahnärzt|tierarzt|tierärzt|palliativ|intensivpfleg|stationsleit|pflegedienst|pflegekraft|pflegehelfer|pflegeassist|betreuungskraft|\bota\b|\bzfa\b|\bbta\b|\bmtr\b|\btfa\b|\bzmf\b|\bzmp\b|\bpka\b|\bmtl\b|\bpflege\b|operationstechnisch"),
    ("Gesundheitswesen (sonstige)", r"ergotherap|physiotherap|logopäd|heilpraktik|osteopath|podolog|ernährungsberat|diätassist|motopäd|musiktherap|kunsttherap|tanztherap|theatertherap|atemtherap|sporttherap|heilpädagog|masseur|sprachtherap|therapeut|augenoptik|optiker|hörakust|hörgeräte|orthoptist|zahntechnik|orthopädietechnik|rehatechnik|sanitätshaus|ökotropholog|oecotropholog"),
    ("Soziale Arbeit & Erziehung", r"sozialarbeit|soziale arbeit|sozial ?arbeiter|sozialpädagog|sozpäd|erzieher|kindheitspädagog|kinderpfleg|jugendhilfe|jugendarbeit|kita|tagesmutter|tagespflege|familienhilfe|heilerziehung|integrationshelfer|schulbegleit|sozialassist|streetwork|pädagog|betreuer|\bhep\b|pfarrer|pastor|diakon|seelsorg|priester|gemeindereferent"),
    ("Bildung & Wissenschaft", r"lehrer|lehrkraft|lehramt|dozent|professor|wissenschaft|forscher|forschung|lektor|schulleit|referendar|erwachsenenbildung|hochschul|doktorand|promov|wiss\.? ?mitarbeit|bildungsreferent|nachhilfe|sonderschul|grundschul|studienrat|studienrät|studiendirekt|oberstudien|soziolog|histori|politolog|germanist|philolog|geograph|geolog|anthropolog|ethnolog|linguist|philosoph|theolog"),
    ("Verwaltung & Büro", r"verwaltung|sachbearbeit|beamt|bürokauf|sekretär|assistenz|assistent|büroang|bürokraft|bürotätigkeit|büromanagement|kauffrau für büro|verwaltungsfach|amtsrat|amtfrau|standesbeamt|justizfach|bürgermeister|fremdsprachenkorrespondent|\bbüro\b|öffentliche[rn]? dienst|referent|arbeitsvermitt|jobcenter|arbeitsagentur"),
    ("IT & Technik", r"ingenieur|dipl\.?[- ]?ing|\bing\.|informatik|software|entwickler|programmier|techniker|mechatronik|elektrotechnik|elektronik|\bit\b|\bedv\b|mathematik|statistik|analyst|product owner|scrum|sysadmin|systemadmin|data ?scientist|datenanalyst|webdesign|webentwickl|devops|technisch|engineer|\bcta\b|physiker|chemiker|biolog|biotechnolog|architekt|bauzeichner|statiker|vermessung|konstrukteur|stadtplan|raumplan|bauleit"),
    ("Wirtschaft, Recht & Finanzen", r"kaufmann|kauffrau|kaufmänn|k(au)?fm\b|betriebswirt|volkswirt|ökonom|manager|management|berater|consultant|controller|buchhalt|steuerfach|steuerberat|wirtschaftsprüf|bank|versicherung|finanz|anwalt|anwält|jurist|richter|notar|rechtspfleg|personalref|personaler|personalleit|\bhr\b|recruiter|marketing|vertrieb|sales|einkäufer|projekt|geschäftsführ|teamleit|abteilungsleit|bereichsleit|filialleit|betriebsleit|standortleit|führungskraft|unternehmensberat|unternehmer|immobilien|makler"),
    ("Handwerk, Produktion & Landwirtschaft", r"handwerk|meister$|meisterin$|metallbau|zimmermann|tischler|schreiner|zimmerer|maurer|maler|lackierer|elektriker|installateur|anlagenmechanik|klempner|dachdecker|friseur|frisör|schneider|bäcker|konditor|metzger|fleischer|mechaniker|kfz|schlosser|schweißer|industriemechanik|produktionsmitarb|produktionsfach|chemikant|maschinenführ|maschinenbedien|anlagenführ|fachkraft für lager|landwirt|gärtner|florist|forstwirt|winzer|brauer|goldschmied|uhrmacher|drucker"),
    ("Dienstleistung, Handel & Verkehr", r"buchhändler|buchhandel|verkäufer|einzelhandel|kassierer|gastronom|koch$|köchin|kellner|servicekraft|hotelfach|restaurantfach|reinigungs|hauswirtschaft|fahrer|lokführer|pilot|zugbegleit|logistik|lagerist|kurier|postbot|zusteller|flugbegleit|kosmetik|nageldesign|tätowier|fitnesstrainer|reiseverkehr|tourismus|sicherheitsdienst|feuerwehr|polizist|polizei|soldat|bundeswehr|zoll|barista|barkeeper|disponent|facility|drogist|trainer|rezeption|empfang|veranstaltung"),
    ("Kunst, Kultur & Medien", r"künstler|musiker|musikpädagog|sänger|schauspieler|regisseur|designer|grafik|illustrator|fotograf|journalist|redakteur|autor|schriftsteller|art direct|creative direct|maskenbildn|restaurator|keramik|presse|öffentlichkeitsarbeit|kommunikationsmanag|texter|übersetzer|dolmetscher|bibliothekar|museum|kurator|galerist|tänzer|choreograf|kameramann|cutter|mediengestalt|moderator|musikschul"),
    ("Nicht erwerbstätig", r"rentner|rentnerin|\brenterin?\b|pension|ruhestand|i\. ?r\.|a\. ?d\.|hausfrau|hausmann|elternzeit|arbeitslos|arbeitssuchend|arbeitsuchend|erwerbsunfähig|erwerbsgemindert|erwerbslos|berufsunfähig|arbeitsunfähig|erwerbsminderung|\brente\b|privatier|mutterschutz|\bmutter\b|\bmama\b|\bvater\b|frührente"),
]
CAT_RES = [(name, re.compile(pat)) for name, pat in CATS]

UNKNOWN_PAT = re.compile(r"^[-–—.,/?!*+\s]*$|^(k\.? ?a\.?|keine ?angabe|keine|kein|egal|privat|geheim|anonym|divers|mensch|bürger|bürgerin|privatperson|xxx*|yyy*|abc|asdf|test|nichts|nix|weiß nicht|-+)$")

def categorize(raw):
    if not isinstance(raw, str) or not raw.strip():
        return "Unbekannt"
    s = raw.strip().lower()
    if UNKNOWN_PAT.fullmatch(s):
        return "Unbekannt"
    for name, rx in CAT_RES:
        if rx.search(s):
            return name
    return "Sonstige"

df["berufskategorie"] = df["berufsbezeichnung"].map(categorize)

# ---------------------------------------------------------------- report
print("=== coverage report ===")
print("\nplz filled:", (df["plz"] != "").sum(), f"({(df['plz'] != '').mean():.1%})")
print("ort_clean filled:", (df["ort_clean"] != "").sum(), f"({(df['ort_clean'] != '').mean():.1%})")
print("ort empty after clean:", (df["ort_clean"] == "").sum())
print("\nhas_academic_title:", df["has_academic_title"].value_counts().to_dict())
n_titles = (df["academic_title_clean"] != "").sum()
print("academic_title_clean non-empty:", n_titles, "unique:", df.loc[df['academic_title_clean'] != '', 'academic_title_clean'].nunique())
print("top cleaned titles:", df.loc[df['academic_title_clean'] != '', 'academic_title_clean'].value_counts().head(15).to_dict())
is_fallback = [(isinstance(r, str) and r.strip() and norm_key(r.strip(" ,;")) not in TITLE_MAP
                and not NO_TITLE.fullmatch(r.strip(" ,;").lower().strip()))
               for r in df["academicTitle"]]
unmapped = df.loc[is_fallback, "academic_title_clean"]
print("titles via keyword-fallback (kept as written):", len(unmapped))
print("top fallback:", unmapped.value_counts().head(25).to_dict())

print("\nberufskategorie distribution:")
print(df["berufskategorie"].value_counts().to_string())
sonst = df.loc[df["berufskategorie"] == "Sonstige", "berufsbezeichnung"]
print("\ntop 40 Sonstige:", sonst.value_counts().head(40).to_dict())
unk = df.loc[df["berufskategorie"] == "Unbekannt", "berufsbezeichnung"].fillna("")
print("\ntop 20 Unbekannt:", unk.value_counts().head(20).to_dict())

if WRITE:
    out = df[["id", "firstName", "lastName", "academic_title_clean", "has_academic_title",
              "berufsbezeichnung", "berufskategorie", "plz", "ort_clean", "createdAt"]].copy()
    out = out.rename(columns={"academic_title_clean": "academicTitle", "ort_clean": "ort"})
    out.to_csv(OUT, index=False, encoding="utf-8")
    print("\nwritten:", OUT, out.shape)
