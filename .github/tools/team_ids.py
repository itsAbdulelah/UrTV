#!/usr/bin/env python3
"""Every club the app's leagues have, and the national teams, with their TheSportsDB ids (run in CI; TheSportsDB is
unreachable from the dev container). The free name search misses some clubs altogether (it never returns the
Saudi Al-Hilal), but every match lists both sides' ids, so a league's recent seasons name all its clubs.

Leagues: the ones the app offers (Prefs.LEAGUES, read from the Java source so the two can't drift). Their ids come
from TheSportsDB's league lists (the general one lacks the Saudi leagues, the per-country one lacks others), and a
few known ids are used only once TheSportsDB confirms the name. National teams are searched by country name.
Checked, not assumed: Al-Hilal must come out as 136013 and Real Madrid as 133738, the ids the app already uses.

Writes teams/teams.json, [{"id", "en", "ar", "leagues"}] with the Arabic name from assets/shared/teams-ar.json
where it has one, and teams/report.json (leagues not found, counts), for review before assets/shared/teams.json.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.thesportsdb.com/api/v1/json/123/"
PREFS = Path("android/app/src/main/java/sa/urtv/screensaver/Prefs.java")
COUNTRIES = ["Saudi Arabia", "England", "Spain", "Italy", "Germany", "France", "Portugal", "Netherlands", "Turkey",
             "Egypt", "United Arab Emirates", "Qatar", "United States"]   # where Prefs.LEAGUES play
GUESSES = {"Portuguese Primeira Liga": "4344", "Turkish Super Lig": "4339"}   # used only if the name matches
SEASONS = ["2025-2026", "2024-2025", "2026", "2025"]   # calendar-year leagues (MLS) use "2026"
ALIASES = {"United States": ["USA", "United States of America"], "Jordan": ["Jordan national football team"]}
NATIONAL = {   # national teams: TheSportsDB's English name -> Arabic
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
KNOWN = {"136013": "Al-Hilal", "133738": "Real Madrid", "136137": "Saudi Arabia"}


def get(path):
    """The free key allows a few requests a minute: pace them and back off on 429."""
    for attempt in range(8):
        time.sleep(4)
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, headers={"User-Agent": "urtv"}),
                                        timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(30 * (attempt + 1))
    raise RuntimeError("rate limited: " + path)


def team_key(name):   # the screen's teamKey(): "Al-Hilal", "Al Hilal SFC" and "AL HILAL" are one club
    s = re.sub(r"\b(fc|sc|cf|afc|club|saudi club)\b", "", str(name).lower())
    return re.sub(r"^al ", "al", re.sub(r"[^a-z0-9]+", " ", s).strip())


def main():
    club_leagues = re.findall(r'\{"([^"]+)", "[^"]+"\}', PREFS.read_text(encoding="utf-8").split("LEAGUES = {")[1]
                              .split("};")[0])
    ids = {l["strLeague"]: l["idLeague"] for l in get("all_leagues.php").get("leagues") or []}
    for country in COUNTRIES:
        if all(n in ids for n in club_leagues):
            break
        found = get("search_all_leagues.php?" + urllib.parse.urlencode({"c": country, "s": "Soccer"}))
        for l in found.get("countries") or found.get("countrys") or found.get("leagues") or []:
            ids.setdefault(l["strLeague"], l["idLeague"])
    for name, i in GUESSES.items():
        if name not in ids:
            confirmed = [l.get("strLeague") for l in get(f"lookupleague.php?id={i}").get("leagues") or []]
            if name in confirmed:
                ids[name] = i
    report = {"leagues not found": [n for n in club_leagues if n not in ids], "teams per league": {},
              "national teams not found": []}
    teams = {}   # id -> {"en", "ar", "leagues"}
    for name in club_leagues:
        if name not in ids:
            continue
        paths = [f"eventsseason.php?id={ids[name]}&s={s}" for s in SEASONS]
        paths += [f"eventspastleague.php?id={ids[name]}", f"eventsnextleague.php?id={ids[name]}"]
        found = set()
        for path in paths:
            for e in get(path).get("events") or []:
                for side in ("Home", "Away"):
                    i, en = e.get(f"id{side}Team"), e.get(f"str{side}Team")
                    if i and en:
                        t = teams.setdefault(i, {"en": en, "ar": "", "leagues": []})
                        if name not in t["leagues"]:
                            t["leagues"].append(name)
                        found.add(i)
        report["teams per league"][name] = len(found)
        print(f"{name}: {len(found)} teams")
    for en, ar in NATIONAL.items():   # the men's team whose name is exactly the country's (or a known alias)
        names, seen, hits = [en] + ALIASES.get(en, []), [], []
        for q in names:
            for t in get("searchteams.php?" + urllib.parse.urlencode({"t": q})).get("teams") or []:
                if t.get("strSport") == "Soccer":
                    seen.append(t.get("strTeam"))
                    if (t.get("strTeam") or "").lower() in {n.lower() for n in names} \
                            and (t.get("strGender") or "Male") == "Male":
                        hits.append(t)
            if hits:
                break
        if hits:
            teams[hits[0]["idTeam"]] = {"en": hits[0]["strTeam"], "ar": ar, "leagues": ["National teams"]}
        else:
            report["national teams not found"].append(f"{en} (search gave: {', '.join(seen[:8]) or 'nothing'})")
    print(len(NATIONAL) - len(report["national teams not found"]), "national teams")
    wrong = {i: n for i, n in KNOWN.items() if team_key(teams.get(i, {}).get("en", "")) != team_key(n)}
    if wrong:
        raise SystemExit(f"these ids didn't come out right, not trusting this: {wrong}")
    # "Al-Faisaly" and "Al Faisaly" are one key but two clubs: the Saudi clubs come first in teams-ar.json,
    # so a club of a Saudi league takes the first Arabic name for its key and any other club the last
    names = json.loads(Path("assets/shared/teams-ar.json").read_text(encoding="utf-8")).items()
    last = {team_key(en): ar for en, ar in names}
    first = {team_key(en): ar for en, ar in reversed(list(names))}

    def arabic(t):
        return (first if any("Saudi" in l for l in t["leagues"]) else last).get(team_key(t["en"]), "")
    out = [{"id": i, "en": t["en"], "ar": t["ar"] or arabic(t), "leagues": t["leagues"]} for i, t in teams.items()]
    order = club_leagues + ["National teams"]
    out.sort(key=lambda t: (order.index(t["leagues"][0]), t["en"]))
    report["teams"] = len(out)
    report["without an Arabic name"] = sum(not t["ar"] for t in out)
    Path("teams").mkdir(exist_ok=True)
    Path("teams/teams.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    Path("teams/report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "teams per league"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
