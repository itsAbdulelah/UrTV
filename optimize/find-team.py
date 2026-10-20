#!/usr/bin/env python3
"""Find a club's TheSportsDB id, by its Arabic or English name, or list a league's clubs to pick from.

    optimize/saver.sh find-team الهلال          a club: every match in our list, Saudi clubs first
    optimize/saver.sh find-team --list Saudi    every club of the leagues whose name has "Saudi"

Our list, assets/shared/teams.json, has every club of the app's leagues and the national teams, with their ids
(built in CI from their matches: TheSportsDB's free search misses some clubs, the Saudi Al-Hilal among them).
Only a club that isn't in it is searched online: Arabic names go through assets/shared/teams-ar.json to their
English spellings, and the usual spellings are tried too (Al-Hilal, Al Hilal, Hilal, … FC).
Prints `id:Name  |  Arabic  |  leagues`, ready for `optimize/saver.sh teams`.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # Windows writes pipes in its own code page
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")

SHARED = Path(__file__).resolve().parents[1] / "assets/shared"
ARABIC = json.loads((SHARED / "teams-ar.json").read_text(encoding="utf-8"))      # English name -> Arabic
try:
    CLUBS = json.loads((SHARED / "teams.json").read_text(encoding="utf-8"))     # [{id, en, ar, leagues}]
except FileNotFoundError:   # an old checkout: search online only
    print("   (assets/shared/teams.json is missing: searching TheSportsDB only)", file=sys.stderr)
    CLUBS = []
API = "https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t="


def plain(ar):   # Arabic compared without harakat, tatweel or hamza forms
    ar = re.sub(r"[\u064B-\u0652\u0640]", "", ar.strip())
    return ar.translate(str.maketrans("أإآة", "اااه"))


def key(name):   # Al-Hilal, Al Hilal, al hilal FC -> alhilal
    return re.sub(r"[^a-z]", "", re.sub(r"\s+(S?FC|F\.C\.|Club)$", "", name.strip(), flags=re.I).lower())


def ours(q):   # the clubs in our list that match: the exact name first, else names that contain it
    if re.search(r"[\u0600-\u06FF]", q):
        english = {key(en) for en, ar in ARABIC.items() if plain(ar) == plain(q)}
        exact = [c for c in CLUBS if (c["ar"] and plain(c["ar"]) == plain(q)) or key(c["en"]) in english]
        return exact or [c for c in CLUBS if c["ar"] and plain(q) in plain(c["ar"])]
    exact = [c for c in CLUBS if key(c["en"]) == key(q)]
    return exact or [c for c in CLUBS if key(q) and key(q) in key(c["en"])]


def show(clubs, limit=15):
    saudi = lambda c: not any("Saudi" in l for l in c["leagues"])   # noqa: E731
    for c in sorted(clubs, key=lambda c: (saudi(c), c["en"]))[:limit]:
        print(f"{c['id']}:{c['en']}  |  {c['ar'] or '-'}  |  {', '.join(c['leagues'])}")


def spellings(name):
    base = re.sub(r"\s+(S?FC|F\.C\.|Club|Football Club)$", "", name.strip(), flags=re.I)
    if " " in base and not re.match(r"Al[- ]", base, flags=re.I):   # Saudi Arabia, Real Madrid: as they are
        return list(dict.fromkeys([name, base]))
    bare = re.sub(r"^Al[- ]", "", base, flags=re.I)
    return list(dict.fromkeys([name, base, f"Al-{bare}", f"Al {bare}", bare]))


def search(name):
    try:
        with urllib.request.urlopen(API + urllib.parse.quote(name), timeout=20) as r:
            return json.load(r).get("teams") or []
    except Exception as e:  # noqa: BLE001
        print(f"   (TheSportsDB didn't answer for {name}: {e})", file=sys.stderr)
        return []


def main():
    q = " ".join(sys.argv[1:]).strip()
    if not q:
        sys.exit("usage: optimize/saver.sh find-team NAME   (Arabic or English)")
    if sys.argv[1] == "--list":
        words = [w.lower() for w in sys.argv[2:]]
        show([c for c in CLUBS if any(all(w in l.lower() for w in words) for l in c["leagues"])] if words else CLUBS,
             limit=None)
        return
    hit = ours(q)
    if hit:
        show(hit)
        return
    if re.search(r"[\u0600-\u06FF]", q):
        names = [en for en, ar in ARABIC.items() if plain(ar) == plain(q)]
        if not names:
            sys.exit(f"«{q}» isn't in our Arabic list (assets/shared/teams-ar.json): try its English name.")
    else:
        names = [q]
    tried, found = set(), {}
    for name in names:   # the Arabic list has many spellings of one club: stop at the first that finds it
        if found:
            break
        for s in spellings(name):
            if s.lower() in tried or len(tried) >= 8:
                continue
            tried.add(s.lower())
            for t in search(s):
                if t.get("strSport") == "Soccer":
                    found[t["idTeam"]] = t
    if not found:
        sys.exit(f"Nothing found for {q} (tried: {', '.join(sorted(tried))}). Try the city, or the English name.")
    for t in sorted(found.values(), key=lambda t: (t.get("strCountry") != "Saudi Arabia", t["strTeam"])):
        print(f"{t['idTeam']}:{t['strTeam']}  |  {t.get('strLeague') or ''}  |  {t.get('strCountry') or ''}")


if __name__ == "__main__":
    main()
