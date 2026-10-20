#!/usr/bin/env python3
"""Every club the app's leagues have, and the national teams, with their TheSportsDB ids and Arabic names (run in
CI: TheSportsDB, Wikidata and Wikipedia are unreachable from the dev container). Monthly too, for promoted and
renamed clubs.

Clubs: the free name search misses some clubs altogether (it never returns the Saudi Al-Hilal), but every match
lists both sides' ids, so each league's last two seasons with matches (and its last and next rounds) name all its
clubs. Leagues are the ones the app offers (Prefs.LEAGUES, read from the Java source so the two can't drift).
National teams are searched by name, else found in their matches against other national teams.

Checked, not assumed: each league's season must have at least LEAGUES[...]["min"] clubs, the KNOWN ids must come out
as the clubs the app already uses, every national team must be found, and each id is looked up on its own
(lookupteam.php, else the team's own matches) to see it names the same team.

Arabic names, best first: our own (national teams below; Saudi clubs from .github/tools/saudi-clubs-ar.json, by
their Arabic Wikipedia article, or assets/shared/teams-ar.json), then Wikidata's Arabic label (the item holding the
club's TheSportsDB id, else its English Wikipedia article, else a search whose description says football club),
then an Arabic name TheSportsDB lists, and only then a transliteration (marked "arFrom": "translit"). Two clubs
never share a name: the Saudi club keeps it and the other gets its country ("العين الإماراتي"); a club named like
a national team becomes «نادي قطر».

Writes teams/teams.json ([{id, en, ar, arFrom, leagues, alt}], the next assets/shared/teams.json), teams/diff.json
and teams/diff.md (added, removed and renamed against assets/shared/teams.json) and teams/report.json. Exits 1 after
writing them if a check failed, so the run shows red with its data still there for review.
"""
import datetime
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://www.thesportsdb.com/api/v1/json/123/"
WIKIDATA = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
ENWIKI = "https://en.wikipedia.org/w/api.php"
UA = "UrTV club list (github.com/tshi-dev/UrTV)"
PREFS = ROOT / "android/app/src/main/java/sa/urtv/screensaver/Prefs.java"
OUT = Path("teams")
NATIONAL_LEAGUE = "National teams"

# Every league in Prefs.LEAGUES: its country (Wikidata's ids for it, for checking a found item), the adjective that
# tells its clubs apart from a namesake ("الإماراتي"), and the fewest clubs one season can have. MLS names its
# seasons by one year ("2026").
LEAGUES = {
    "Saudi-Arabian Pro League": {"country": "Saudi Arabia", "wd": {"Q851"}, "adj": "السعودي", "min": 18},
    "Saudi First Division League": {"country": "Saudi Arabia", "wd": {"Q851"}, "adj": "السعودي", "min": 18},
    "English Premier League": {"country": "England", "wd": {"Q21", "Q145", "Q25"}, "adj": "الإنجليزي", "min": 20},
    "Spanish La Liga": {"country": "Spain", "wd": {"Q29"}, "adj": "الإسباني", "min": 20},
    "Italian Serie A": {"country": "Italy", "wd": {"Q38"}, "adj": "الإيطالي", "min": 20},
    "German Bundesliga": {"country": "Germany", "wd": {"Q183"}, "adj": "الألماني", "min": 18},
    "French Ligue 1": {"country": "France", "wd": {"Q142"}, "adj": "الفرنسي", "min": 18},
    "Portuguese Primeira Liga": {"country": "Portugal", "wd": {"Q45"}, "adj": "البرتغالي", "min": 18},
    "Dutch Eredivisie": {"country": "Netherlands", "wd": {"Q55", "Q29999"}, "adj": "الهولندي", "min": 18},
    "Turkish Super Lig": {"country": "Turkey", "wd": {"Q43"}, "adj": "التركي", "min": 18},
    "Egyptian Premier League": {"country": "Egypt", "wd": {"Q79"}, "adj": "المصري", "min": 18},
    "UAE Pro League": {"country": "United Arab Emirates", "wd": {"Q878"}, "adj": "الإماراتي", "min": 14},
    "Qatar Stars League": {"country": "Qatar", "wd": {"Q846"}, "adj": "القطري", "min": 12},
    "American Major League Soccer": {"country": "United States", "wd": {"Q30", "Q16"}, "adj": "الأمريكي", "min": 30,
                                     "calendar": True},
}
GUESSES = {"Portuguese Primeira Liga": "4344", "Turkish Super Lig": "4339"}   # used only if the name matches
ALIASES = {"United States": ["USA", "United States of America"], "Jordan": ["Jordan national football team"],
           "South Korea": ["Korea Republic"], "Iran": ["IR Iran"], "China": ["China PR"]}
NATIONAL = {   # national teams: TheSportsDB's English name -> our Arabic name
    "Saudi Arabia": "السعودية", "United Arab Emirates": "الإمارات", "Qatar": "قطر", "Kuwait": "الكويت",
    "Bahrain": "البحرين", "Oman": "عمان", "Iraq": "العراق", "Jordan": "الأردن", "Syria": "سوريا", "Lebanon": "لبنان",
    "Palestine": "فلسطين", "Yemen": "اليمن", "Egypt": "مصر", "Morocco": "المغرب", "Algeria": "الجزائر",
    "Tunisia": "تونس", "Libya": "ليبيا", "Sudan": "السودان", "Iran": "إيران", "Japan": "اليابان",
    "South Korea": "كوريا الجنوبية", "Australia": "أستراليا", "China": "الصين", "Uzbekistan": "أوزبكستان",
    "Brazil": "البرازيل", "Argentina": "الأرجنتين", "France": "فرنسا", "England": "إنجلترا", "Spain": "إسبانيا",
    "Germany": "ألمانيا", "Italy": "إيطاليا", "Portugal": "البرتغال", "Netherlands": "هولندا", "Belgium": "بلجيكا",
    "Croatia": "كرواتيا", "United States": "الولايات المتحدة", "Mexico": "المكسيك", "Uruguay": "الأوروغواي",
    "Colombia": "كولومبيا", "Senegal": "السنغال", "Nigeria": "نيجيريا", "Cameroon": "الكاميرون", "Turkey": "تركيا",
}
# a national team the search misses is looked for in its matches against these
PARTNERS = ["Saudi Arabia", "Iraq", "Qatar", "United Arab Emirates", "Kuwait", "Oman", "Bahrain", "Palestine",
            "Syria", "Lebanon", "Egypt", "Morocco", "South Korea", "Japan"]
KNOWN = {"136013": "Al-Hilal", "136022": "Al-Nassr", "133738": "Real Madrid", "133604": "Arsenal",
         "136137": "Saudi Arabia"}
HILAL_ARTICLE = "نادي الهلال (السعودية)"   # Al-Hilal's Arabic Wikipedia article: finds Wikidata's TheSportsDB property

FOOTBALL = re.compile(r"football|soccer", re.I)
NOT_A_CLUB = re.compile(r"women|female|ladies|futsal|basketball|handball|volleyball|youth|under-\d|reserve", re.I)
# letters Thmanyah (the screen's font) lacks, as Arabic writes them
FONT_FIX = str.maketrans({"گ": "ج", "ژ": "ج", "ڨ": "ق", "ی": "ي", "ک": "ك", "ۀ": "ه", "ہ": "ه", "ھ": "ه", "ە": "ه",
                          "ۆ": "و", "ٱ": "ا"})
ARABIC_NAME = re.compile(r"[ء-غف-ي٠-٩پچڤ \-]+")


# ---------- the network (the free TheSportsDB key allows about 30 requests a minute) ----------

def fetch(url, data=None, headers=None, pause=2.2, tries=8):
    for attempt in range(tries):
        time.sleep(pause)
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(30 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("no answer: " + url[:200])


def get(path):
    return fetch(API + path) or {}


def wiki(api, params):
    d = fetch(api + "?" + urllib.parse.urlencode({**params, "format": "json", "maxlag": "5"}), pause=1)
    if (d.get("error") or {}).get("code") == "maxlag":
        time.sleep(10)
        d = fetch(api + "?" + urllib.parse.urlencode({**params, "format": "json", "maxlag": "5"}), pause=1)
    return d


# ---------- names ----------

def team_key(name):   # the screen's teamKey(): "Al-Hilal", "Al Hilal SFC" and "AL HILAL" are one club
    s = re.sub(r"\b(fc|sc|cf|afc|club|saudi club)\b", "", str(name).lower())
    return re.sub(r"^al ", "al", re.sub(r"[^a-z0-9]+", " ", s).strip())


def latin(name):   # "Atlético" -> "atletico", for comparing names
    s = unicodedata.normalize("NFKD", str(name).replace("ı", "i").replace("ß", "ss"))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


GENERIC = {"fc", "sc", "cf", "afc", "club", "al", "el", "de", "the", "and", "city", "united", "real", "sporting",
           "football", "soccer", "sport", "sports", "saudi", "cd", "ud", "sd", "ac", "as", "ss", "us", "sv", "vfb",
           "vfl", "tsg", "rc", "ca", "fk", "sk"}


def same_team(a, b):   # one name holds a distinctive word of the other ("Paris SG", "Paris Saint-Germain F.C.")
    if team_key(a) == team_key(b):
        return True
    wa = {w for w in latin(a).split() if len(w) >= 3 and w not in GENERIC}
    wb = {w for w in latin(b).split() if len(w) >= 3 and w not in GENERIC}
    return bool(wa & wb) or (latin(a).replace(" ", "") in latin(b).replace(" ", "")) \
        or (latin(b).replace(" ", "") in latin(a).replace(" ", ""))


def plain_ar(s):   # Arabic compared without harakat or hamza forms
    s = re.sub(r"[ً-ٰٟـ]", "", str(s))
    return re.sub(r"\s+", " ", s.translate(str.maketrans("أإآٱةى", "ااااهي"))).strip()


def clean_ar(label):
    """Wikidata's «نادي العين (الإمارات)» -> «العين»; '' if it isn't plain Arabic the screen's font can draw."""
    s = re.sub(r"[ً-ٰٟـ]", "", str(label or "")).translate(FONT_FIX)
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    s = re.sub(r"^(?:(?:ال)?نادي|فريق)(?:\s+|$)", "", s)
    s = re.sub(r"\s+(?:لكرة القدم|الرياضي|للألعاب الرياضية)$", "", s).strip()
    return s if ARABIC_NAME.fullmatch(s) and len(s.replace(" ", "")) >= 2 else ""


# the screen's translit() (src/template.html), for the names nothing else gives: tests/team_ids_test.py compares them
TL_WORDS = {"the": "ذا", "of": "أوف", "and": "آند", "a": "إيه", "in": "إن", "on": "أون", "to": "تو", "us": "أس",
            "fc": "", "cf": "", "sc": "", "afc": "", "united": "يونايتد", "city": "سيتي", "real": "ريال",
            "club": "كلوب", "sporting": "سبورتنغ", "saint": "سانت", "st": "سانت"}
TL_LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", "إيه بي سي دي إي إف جي إتش آي جيه كيه إل إم إن أو بي كيو آر إس تي "
                      "يو في دبليو إكس واي زد".split()))
TL_MAP = {"sh": "ش", "kh": "خ", "th": "ث", "dh": "ذ", "gh": "غ", "ch": "تش", "ph": "ف", "ck": "ك", "qu": "كو",
          "ou": "و", "oo": "و", "ee": "ي", "a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف", "g": "ج",
          "h": "ه", "i": "ي", "j": "ج", "k": "ك", "l": "ل", "m": "م", "n": "ن", "o": "و", "p": "ب", "q": "ق", "r": "ر",
          "s": "س", "t": "ت", "u": "و", "v": "ف", "w": "و", "x": "كس", "y": "ي", "z": "ز"}
TL_START = {"a": "أ", "e": "إ", "i": "إ", "o": "أو", "u": "أ"}


def translit(en):
    def word(w):
        if re.search("[؀-ۿ]", w) or not re.search("[A-Za-z0-9]", w):
            return w
        lw = w.lower()
        if lw in TL_WORDS:
            return TL_WORDS[lw]
        if re.fullmatch("[A-Z]{2,4}", w):   # CP, PSG
            return " ".join(TL_LETTERS[c] for c in lw)
        if lw.startswith("al-"):
            return "ال" + word(w[3:])
        out, x, i = "", re.sub(r"(.)\1", r"\1", lw), 0
        while i < len(x):
            two = TL_MAP.get(x[i:i + 2]) if i + 1 < len(x) else None
            if i == 0 and x[0] in TL_START and not two:
                out, i = out + TL_START[x[0]], i + 1
                continue
            if two:
                out, i = out + two, i + 2
                continue
            ch = x[i]
            if ch == "e" and i > 0:   # short or silent e
                i += 1
                continue
            if ch == "c" and re.fullmatch("[eiy]", x[i + 1:i + 2] or "-"):
                out, i = out + "س", i + 1
                continue
            out += chr(0x0660 + int(ch)) if ch in "0123456789" else TL_MAP.get(ch, "")
            i += 1
        return out
    s = re.sub(r"\bAl (?=[A-Z])", "Al-", str(en).replace("&", " و "), flags=re.A)
    return re.sub(r"\s{2,}", " ", "".join(word(w) for w in re.split(r"(\s+)", s))).strip()


# ---------- clubs from their leagues' matches ----------

def seasons_to_try(league, today):
    if league.get("calendar"):
        return [str(today.year - k) for k in range(3)]
    y = today.year if today.month >= 7 else today.year - 1   # a season starts in July or August
    return [f"{y - k}-{y - k + 1}" for k in range(3)]


def sides(events):
    for e in events or []:
        for side in ("Home", "Away"):
            i, en = e.get(f"id{side}Team"), e.get(f"str{side}Team")
            if i and en:
                yield str(i), en.strip()


def league_ids(names):
    ids = {l["strLeague"]: l["idLeague"] for l in get("all_leagues.php").get("leagues") or []}
    for country in dict.fromkeys(LEAGUES[n]["country"] for n in names if n in LEAGUES):
        if all(n in ids for n in names):
            break
        found = get("search_all_leagues.php?" + urllib.parse.urlencode({"c": country, "s": "Soccer"}))
        for l in found.get("countries") or found.get("countrys") or found.get("leagues") or []:
            ids.setdefault(l["strLeague"], l["idLeague"])
    for name, i in GUESSES.items():
        if name in names and name not in ids:
            if name in [l.get("strLeague") for l in get(f"lookupleague.php?id={i}").get("leagues") or []]:
                ids[name] = i
    return ids


def collect_league(name, lid, today, teams, report, problems):
    """The clubs of the last two seasons that have matches, and of the last and next rounds."""
    seasons = {}
    for s in seasons_to_try(LEAGUES[name], today):
        if len(seasons) == 2:
            break
        found = dict(sides(get(f"eventsseason.php?id={lid}&s={s}").get("events")))
        if found:
            seasons[s] = found
    rounds = {}
    for path in (f"eventspastleague.php?id={lid}", f"eventsnextleague.php?id={lid}"):
        rounds.update(sides(get(path).get("events")))
    every = {}
    for found in [*seasons.values(), rounds]:
        every.update(found)
    for i, en in every.items():
        t = teams.setdefault(i, {"en": en, "leagues": []})
        if name not in t["leagues"]:
            t["leagues"].append(name)
    report["clubs per league"][name] = {"clubs": len(every), "seasons": {s: len(f) for s, f in seasons.items()},
                                        "last and next rounds": len(rounds)}
    print(f"{name}: {len(every)} clubs {report['clubs per league'][name]['seasons']}", flush=True)
    if len(seasons) < 2:
        problems.append(f"{name}: matches found for {len(seasons)} of the last two seasons")
    for s, found in seasons.items():
        if len(found) < LEAGUES[name]["min"]:
            problems.append(f"{name} {s}: {len(found)} clubs, at least {LEAGUES[name]['min']} expected")


def find_national(en, teams, report):
    """The men's team named exactly as the country (or a known alias); else from its matches with other teams."""
    names = [en] + ALIASES.get(en, [])
    wanted = {n.lower() for n in names}
    seen = []
    for q in names:
        for t in get("searchteams.php?" + urllib.parse.urlencode({"t": q})).get("teams") or []:
            if t.get("strSport") == "Soccer":
                seen.append(t.get("strTeam"))
                if (t.get("strTeam") or "").lower() in wanted and (t.get("strGender") or "Male") == "Male":
                    return str(t["idTeam"]), t["strTeam"]
    known = {t["en"]: i for i, t in teams.items() if NATIONAL_LEAGUE in t["leagues"]}
    for partner in [p for p in PARTNERS if p != en and p in known][:8]:
        for a, b in ((en, partner), (partner, en)):
            q = f"{a} vs {b}".replace(" ", "_")
            for i, name in sides(get("searchevents.php?" + urllib.parse.urlencode({"e": q})).get("event")):
                if name.lower() in wanted and i != known[partner]:
                    report["national teams found in their matches"].append(f"{en}: {i} ({q})")
                    return i, name
    report["national teams not found"].append(f"{en} (search gave: {', '.join(seen[:8]) or 'nothing'})")
    return None


def verify(teams, report):
    """Look each id up on its own: lookupteam.php if it answers the KNOWN ids right, else the team's own matches."""
    def lookup(i):
        hit = (get(f"lookupteam.php?id={i}").get("teams") or [None])[0]
        return hit if hit and str(hit.get("idTeam")) == i else None
    usable = all((lambda t: t and team_key(t.get("strTeam")) == team_key(n))(lookup(i)) for i, n in KNOWN.items())
    report["ids checked with"] = "lookupteam.php" if usable else "the team's own matches"
    checks = report["id checks"]
    for i, t in teams.items():
        if usable:
            hit = lookup(i)
            if not hit:
                checks["no answer"].append(f"{i} {t['en']}")
                continue
            alt = [a.strip() for a in re.split(r"[,;/]", hit.get("strTeamAlternate") or "") if a.strip()]
            t["lookup"] = {"name": hit.get("strTeam") or "", "alt": alt, "country": hit.get("strCountry") or "",
                           "gender": hit.get("strGender") or ""}
            if not any(same_team(t["en"], n) for n in [hit.get("strTeam") or ""] + alt):
                checks["another name"].append(f"{i}: {t['en']} in the matches, {hit.get('strTeam')} on its own")
            elif t["lookup"]["gender"] and t["lookup"]["gender"] != "Male":
                checks["another name"].append(f"{i}: {t['en']} is a {t['lookup']['gender']} team")
            else:
                checks["same team"] += 1
        else:
            names = []
            for path in (f"eventslast.php?id={i}", f"eventsnext.php?id={i}"):
                d = get(path)
                names = [n for j, n in sides(d.get("results") or d.get("events")) if j == i]
                if names:
                    break
            if not names:
                checks["no answer"].append(f"{i} {t['en']}")
            elif not any(same_team(t["en"], n) for n in names):
                checks["another name"].append(f"{i}: {t['en']} in the league, {names[0]} in its own matches")
            else:
                checks["same team"] += 1


# ---------- Arabic names ----------

def wikidata_arabic(teams, report):
    """{TheSportsDB id: (Arabic label, Arabic Wikipedia title, English label)} from Wikidata, matched by id first."""
    found, notes = {}, report["wikidata"]
    try:
        d = wiki(WIKIDATA, {"action": "wbgetentities", "sites": "arwiki", "titles": HILAL_ARTICLE, "props": "claims"})
        hilal = next(iter(d.get("entities", {}).values()), {})
        props = [p for p, claims in hilal.get("claims", {}).items()
                 if any(((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") == "136013" for c in claims)]
        notes["TheSportsDB property"] = props
        if len(props) == 1:
            ids = list(teams)
            for k in range(0, len(ids), 150):
                values = " ".join(f'"{i}"' for i in ids[k:k + 150])
                q = f"""SELECT ?id ?item ?ar ?en ?arTitle ?desc WHERE {{
                  VALUES ?id {{ {values} }} ?item wdt:{props[0]} ?id .
                  OPTIONAL {{ ?item rdfs:label ?ar FILTER(LANG(?ar) = "ar") }}
                  OPTIONAL {{ ?item rdfs:label ?en FILTER(LANG(?en) = "en") }}
                  OPTIONAL {{ ?item schema:description ?desc FILTER(LANG(?desc) = "en") }}
                  OPTIONAL {{ ?a schema:about ?item; schema:isPartOf <https://ar.wikipedia.org/>; schema:name ?arTitle }}
                }}"""
                rows = fetch(SPARQL, data=urllib.parse.urlencode({"query": q}).encode(), pause=2,
                             headers={"Accept": "application/sparql-results+json"})["results"]["bindings"]
                by_id = {}
                for r in rows:
                    by_id.setdefault(r["id"]["value"], {})[r["item"]["value"]] = {k: v["value"] for k, v in r.items()}
                for i, items in by_id.items():
                    good = [v for v in items.values() if not NOT_A_CLUB.search(v.get("desc", ""))
                            and same_team(teams[i]["en"], v.get("en", ""))]
                    if len(good) != 1:
                        notes["ids on several or unlike items"].append(f"{i} {teams[i]['en']}: "
                                                                       + ", ".join(v.get("en", "?") for v in items.values()))
                        continue
                    found[i] = (good[0].get("ar", ""), good[0].get("arTitle", ""), good[0].get("en", ""), "id")
        notes["matched by id"] = len(found)
    except Exception as e:  # noqa: BLE001  (Wikidata down: the other sources still give names)
        notes["error (by id)"] = repr(e)[:300]
    try:
        by_name(teams, found, notes)
    except Exception as e:  # noqa: BLE001
        notes["error (by name)"] = repr(e)[:300]
    return found


def by_name(teams, found, notes):
    """Clubs Wikidata doesn't hold the id of: their English Wikipedia article, else a search, with checks."""
    left = [i for i, t in teams.items() if i not in found and NATIONAL_LEAGUE not in t["leagues"]]
    titles = {}   # club id -> titles to try, best first
    for i in left:
        t = teams[i]
        base = [t["en"]] + [a for a in (t.get("lookup") or {}).get("alt", []) if re.fullmatch(r"[ -~À-ž]+", a)]
        titles[i] = list(dict.fromkeys(x for b in base[:3] for x in (b, b + " FC", b + " F.C.", b + " SC")))
    qid = {}   # title -> Wikidata id
    flat = list(dict.fromkeys(x for v in titles.values() for x in v))
    for k in range(0, len(flat), 50):
        d = wiki(ENWIKI, {"action": "query", "titles": "|".join(flat[k:k + 50]), "redirects": 1, "prop": "pageprops",
                          "ppprop": "wikibase_item|disambiguation"}).get("query", {})
        to = {x["from"]: x["to"] for x in d.get("normalized", []) + d.get("redirects", [])}
        pages = {p.get("title"): p.get("pageprops", {}) for p in d.get("pages", {}).values()}
        for title in flat[k:k + 50]:
            final = title
            for _ in range(3):
                final = to.get(final, final)
            props = pages.get(final) or {}
            if props.get("wikibase_item") and "disambiguation" not in props:
                qid[title] = props["wikibase_item"]
    candidates = {}   # club id -> [Wikidata ids], article first, then search hits
    for i in left:
        candidates[i] = list(dict.fromkeys(qid[x] for x in titles[i] if x in qid))
        if not candidates[i]:
            d = wiki(WIKIDATA, {"action": "wbsearchentities", "search": teams[i]["en"], "language": "en",
                                "type": "item", "limit": 7})
            candidates[i] = [h["id"] for h in d.get("search", []) if FOOTBALL.search(h.get("description", ""))]
    every = list(dict.fromkeys(q for v in candidates.values() for q in v))
    entities = {}
    for k in range(0, len(every), 50):
        d = wiki(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(every[k:k + 50]),
                            "props": "labels|descriptions|claims|sitelinks", "languages": "ar|en", "sitefilter": "arwiki"})
        entities.update(d.get("entities", {}))
    for i in left:
        country = set().union(*(LEAGUES[l]["wd"] for l in teams[i]["leagues"] if l in LEAGUES))
        for q in candidates[i]:
            e = entities.get(q) or {}
            desc = ((e.get("descriptions") or {}).get("en") or {}).get("value", "")
            en = ((e.get("labels") or {}).get("en") or {}).get("value", "")
            where = {((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
                     for c in (e.get("claims") or {}).get("P17", [])}
            if not FOOTBALL.search(desc) or NOT_A_CLUB.search(desc) or (where and country and not where & country) \
                    or not same_team(teams[i]["en"], en):
                continue
            found[i] = (((e.get("labels") or {}).get("ar") or {}).get("value", ""),
                        ((e.get("sitelinks") or {}).get("arwiki") or {}).get("title", ""), en, "name")
            break
    notes["matched by name"] = sum(1 for v in found.values() if v[3] == "name")


def curated():
    """teams-ar.json by name key: Saudi clubs come first in it, so a Saudi club takes the first name for its key
    ("Al-Faisaly" is Saudi, "Al Faisaly" Jordanian) and any other club the last."""
    names = list(json.loads((ROOT / "assets/shared/teams-ar.json").read_text(encoding="utf-8")).items())
    last = {team_key(en): ar for en, ar in names}
    first = {team_key(en): ar for en, ar in reversed(names)}
    saudi = {c["article"]: c["ar"] for c in json.loads((ROOT / ".github/tools/saudi-clubs-ar.json")
                                                       .read_text(encoding="utf-8"))}
    return first, last, saudi


def is_saudi(t):
    return any(l in LEAGUES and LEAGUES[l]["country"] == "Saudi Arabia" for l in t["leagues"])


def arabic_names(teams, wd, report):
    first, last, saudi = curated()
    for i, t in teams.items():
        w = wd.get(i)
        alt_ar = [clean_ar(a) for a in (t.get("lookup") or {}).get("alt", []) if re.search("[؀-ۿ]", a)]
        options = []
        if NATIONAL_LEAGUE in t["leagues"]:
            options.append((t.get("ar", ""), "curated"))
        if is_saudi(t):
            options += [(saudi.get(w[1], "") if w else "", "curated"), (first.get(team_key(t["en"]), ""), "curated")]
        else:
            options.append((last.get(team_key(t["en"]), ""), "curated"))
        if w:
            options += [(clean_ar(w[0]), "wikidata"), (clean_ar(w[1]), "wikidata")]
        options += [(a, "thesportsdb") for a in alt_ar]
        options.append((translit(t["en"]), "translit"))
        t["ar"], t["arFrom"] = next((a, src) for a, src in options if a)
    report["Arabic names from"] = {src: sum(t["arFrom"] == src for t in teams.values())
                                   for src in ("curated", "wikidata", "thesportsdb", "translit")}


def country_adj(t):
    return next((LEAGUES[l]["adj"] for l in t["leagues"] if l in LEAGUES), "")


def unique_names(teams, report, problems):
    """No two teams share an Arabic name: national teams and Saudi clubs keep theirs, others add their country."""
    def groups():
        g = {}
        for i, t in teams.items():
            g.setdefault(plain_ar(t["ar"]), []).append(i)
        return [v for v in g.values() if len(v) > 1]
    for ids in groups():
        national = [i for i in ids if NATIONAL_LEAGUE in teams[i]["leagues"]]
        saudi = [i for i in ids if i not in national and is_saudi(teams[i])]
        keep = (national or saudi)[:1]
        for i in ids:
            if i in keep:
                continue
            t, before = teams[i], teams[i]["ar"]
            if national:
                t["ar"] = "نادي " + t["ar"]
            elif country_adj(t) and not t["ar"].endswith(country_adj(t)):
                t["ar"] = f"{t['ar']} {country_adj(t)}"
            report["names told apart"].append(f"{i} {t['en']}: {before} -> {t['ar']}")
    for ids in groups():   # still the same: two clubs of one country, or a name that already had its country
        for i in ids[1:]:
            t, before = teams[i], teams[i]["ar"]
            t["ar"] = f"{t['ar']} ({translit(t['en'])})"
            report["names told apart"].append(f"{i} {t['en']}: {before} -> {t['ar']}")
    for ids in groups():
        problems.append("one Arabic name for several teams: " + ", ".join(f"{i} {teams[i]['en']}" for i in ids))


# ---------- review ----------

def diff(old, new):
    """Added, removed and renamed teams, and teams that changed leagues, for the monthly review."""
    o, n = {t["id"]: t for t in old}, {t["id"]: t for t in new}
    brief = lambda t: {k: t.get(k) for k in ("id", "en", "ar", "leagues")}   # noqa: E731
    return {
        "added": [brief(n[i]) for i in n if i not in o],
        "removed": [brief(o[i]) for i in o if i not in n],
        "renamed": [{"id": i, "en": [o[i]["en"], n[i]["en"]], "ar": [o[i].get("ar"), n[i]["ar"]]}
                    for i in n if i in o and (o[i]["en"] != n[i]["en"] or o[i].get("ar") != n[i]["ar"])],
        "leagues changed": [{"id": i, "en": n[i]["en"], "leagues": [o[i]["leagues"], n[i]["leagues"]]}
                            for i in n if i in o and o[i]["leagues"] != n[i]["leagues"]],
    }


def diff_md(d, old_count, new_count):
    lines = [f"# Clubs list: {old_count} -> {new_count} teams", ""]
    for kind in ("added", "removed"):
        lines += [f"## {kind.capitalize()} ({len(d[kind])})", ""]
        lines += [f"- {t['id']} {t['en']} «{t['ar']}» ({', '.join(t['leagues'])})" for t in d[kind]] or ["- none"]
        lines.append("")
    lines += [f"## Renamed ({len(d['renamed'])})", ""]
    lines += [f"- {t['id']} {' -> '.join(dict.fromkeys(t['en']))} «{t['ar'][0]}» -> «{t['ar'][1]}»"
              for t in d["renamed"]] or ["- none"]
    lines += ["", f"## Leagues changed ({len(d['leagues changed'])})", ""]
    lines += [f"- {t['id']} {t['en']}: {', '.join(t['leagues'][0])} -> {', '.join(t['leagues'][1])}"
              for t in d["leagues changed"]] or ["- none"]
    return "\n".join(lines) + "\n"


def alt_names(t):
    names = [t.get("lookup", {}).get("name", "")] + t.get("lookup", {}).get("alt", []) + [t.get("wd_en", "")]
    out = []
    for a in names:
        a = a.strip()
        if a and not re.search("[؀-ۿ]", a) and team_key(a) != team_key(t["en"]) \
                and team_key(a) not in {team_key(x) for x in out}:
            out.append(a)
    return out[:4]


def main():
    today = datetime.date.today()
    club_leagues = re.findall(r'\{"([^"]+)", "[^"]+"\}', PREFS.read_text(encoding="utf-8").split("LEAGUES = {")[1]
                              .split("};")[0])
    problems = [f"{n} is in Prefs.LEAGUES but not in team_ids.py's LEAGUES (country, minimum)"
                for n in club_leagues if n not in LEAGUES]
    report = {"date": today.isoformat(), "problems": problems, "clubs per league": {},
              "national teams found in their matches": [], "national teams not found": [],
              "id checks": {"same team": 0, "another name": [], "no answer": []},
              "wikidata": {"ids on several or unlike items": []}, "names told apart": []}
    ids = league_ids([n for n in club_leagues if n in LEAGUES])
    problems += [f"league not found on TheSportsDB: {n}" for n in club_leagues if n in LEAGUES and n not in ids]
    teams = {}   # id -> {"en", "leagues", ...}
    for name in club_leagues:
        if name in LEAGUES and name in ids:
            collect_league(name, ids[name], today, teams, report, problems)
    for en, ar in NATIONAL.items():
        hit = find_national(en, teams, report)
        if hit:
            teams.setdefault(hit[0], {"en": hit[1], "leagues": []})
            teams[hit[0]].update(ar=ar)
            teams[hit[0]]["leagues"].append(NATIONAL_LEAGUE)
    print(len(NATIONAL) - len(report["national teams not found"]), "of", len(NATIONAL), "national teams", flush=True)
    problems += [f"national team not found: {x}" for x in report["national teams not found"]]
    wrong = {i: n for i, n in KNOWN.items() if team_key(teams.get(i, {}).get("en", "")) != team_key(n)}
    if wrong:
        problems.append(f"these ids didn't come out right: {wrong}")
    verify(teams, report)
    print("ids:", {k: v if isinstance(v, int) else len(v) for k, v in report["id checks"].items()}, flush=True)
    wd = wikidata_arabic(teams, report)
    for i, w in wd.items():
        teams[i]["wd_en"] = w[2]
    arabic_names(teams, wd, report)
    unique_names(teams, report, problems)
    problems += [f"Saudi club or national team named only by transliteration: {i} {t['en']}"
                 for i, t in teams.items() if t["arFrom"] == "translit" and (is_saudi(t) or NATIONAL_LEAGUE in t["leagues"])]
    order = club_leagues + [NATIONAL_LEAGUE]
    out = [{"id": i, "en": t["en"], "ar": t["ar"], "arFrom": t["arFrom"], "leagues": t["leagues"], "alt": alt_names(t)}
           for i, t in teams.items()]
    out.sort(key=lambda t: (order.index(t["leagues"][0]), t["en"]))
    report["teams"] = len(out)
    try:
        old = json.loads((ROOT / "assets/shared/teams.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        old = []
    d = diff(old, out)
    OUT.mkdir(exist_ok=True)
    (OUT / "teams.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "diff.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "diff.md").write_text(diff_md(d, len(old), len(out)), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("clubs per league", "names told apart")},
                     ensure_ascii=False, indent=1))
    print({k: len(v) for k, v in d.items()})
    if problems:
        print("\nPROBLEMS:\n- " + "\n- ".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main()
