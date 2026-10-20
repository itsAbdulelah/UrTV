#!/usr/bin/env python3
"""The clubs collector's offline parts (.github/tools/team_ids.py): its transliteration is the screen's translit()
(run in node from src/template.html), Wikidata labels are cleaned, no two teams keep one Arabic name, and the
monthly diff names what changed. Run: python3 tests/team_ids_test.py"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("team_ids", ROOT / ".github/tools/team_ids.py")
ti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti)
failed = 0


def check(name, ok, detail=""):
    global failed
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {detail}"))
    failed += not ok


# transliteration: the same as the screen's, on every English name in the list and a few hard ones
names = [c["en"] for c in json.loads((ROOT / "assets/shared/teams.json").read_text(encoding="utf-8"))]
names += ["Al-Hilal", "PSG", "St. Louis City SC", "Brighton & Hove Albion", "1. FC Köln", "Schalke 04", "AC Milan",
          "Ceará", "Cercle Brugge", "Al Ain", "  Two  Spaces ", "Queens Park Rangers", "Chelsea"]
node = shutil.which("node")
if not node:
    print("SKIP translit against the screen: no node here")
else:
    page = (ROOT / "src/template.html").read_text(encoding="utf-8")
    start = page.index("const TL_WORDS")
    end = page.index("async function wikidataArabic")
    js = ("const hasArabic = s => /[؀-ۿ]/.test(s);\nconst ar = d => String(d).replace(/[0-9]/g, c => "
          "String.fromCharCode(0x660 + +c));\n" + page[start:end]
          + "\nprocess.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0, 'utf8')).map(translit)));")
    r = subprocess.run([node, "-e", js], input=json.dumps(names), capture_output=True, text=True, encoding="utf-8")
    check("node runs the screen's translit()", r.returncode == 0, r.stderr[-400:])
    if r.returncode == 0:
        screen = json.loads(r.stdout)
        differ = [(n, s, ti.translit(n)) for n, s in zip(names, screen) if s != ti.translit(n)]
        check(f"translit: the screen's on all {len(names)} names", not differ, differ[:6])

for label, want in [("نادي العين (الإمارات)", "العين"), ("النادي الأهلي (قطر)", "الأهلي"), ("فريق الوصل", "الوصل"),
                    ("نادي ريال مدريد لكرة القدم", "ريال مدريد"), ("ريَال", "ريال"), ("گوتنبرغ", "جوتنبرغ"),
                    ("Al Ain", ""), ("", ""), ("ا", ""), ("نادي (قطر)", "")]:
    check(f"clean_ar({label!r}) = {want!r}", ti.clean_ar(label) == want, ti.clean_ar(label))

# names told apart: the Saudi club and the national team keep theirs
teams = {
    "1": {"en": "Al-Ain", "ar": "العين", "leagues": ["Saudi First Division League"], "arFrom": "curated"},
    "2": {"en": "Al Ain", "ar": "العين", "leagues": ["UAE Pro League"], "arFrom": "curated"},
    "3": {"en": "Qatar", "ar": "قطر", "leagues": ["National teams"], "arFrom": "curated"},
    "4": {"en": "Qatar SC", "ar": "قطر", "leagues": ["Qatar Stars League"], "arFrom": "curated"},
    "5": {"en": "Al-Arabi", "ar": "العربي", "leagues": ["Qatar Stars League"], "arFrom": "wikidata"},
    "6": {"en": "Al-Arabi Al-Saudi", "ar": "العربي", "leagues": ["Saudi First Division League"], "arFrom": "curated"},
    "7": {"en": "Al Ahly", "ar": "الأهلي المصري", "leagues": ["Egyptian Premier League"], "arFrom": "curated"},
    "8": {"en": "Al-Ahly Benghazi", "ar": "الاهلي المصري", "leagues": ["Egyptian Premier League"], "arFrom": "wikidata"},
    "9": {"en": "Al-Ahli", "ar": "الأهلي", "leagues": ["Saudi-Arabian Pro League"], "arFrom": "curated"},
}
report, problems = {"names told apart": []}, []
ti.unique_names(teams, report, problems)
got = {i: t["ar"] for i, t in teams.items()}
check("Saudi Al-Ain keeps «العين», the Emirati one gets its country", got["1"] == "العين" and got["2"] == "العين الإماراتي", got)
check("the national team keeps «قطر», the club becomes «نادي قطر»", got["3"] == "قطر" and got["4"] == "نادي قطر", got)
check("Saudi Al-Arabi keeps «العربي», Qatar's gets «العربي القطري»", got["6"] == "العربي" and got["5"] == "العربي القطري", got)
check("two names that differ only in hamza are told apart too", ti.plain_ar(got["7"]) != ti.plain_ar(got["8"]), got)
check("no names left shared", len({ti.plain_ar(a) for a in got.values()}) == len(got) and not problems, (got, problems))

# the monthly diff
old = [{"id": "1", "en": "Al-Ain", "ar": "العين", "leagues": ["Saudi First Division League"]},
       {"id": "2", "en": "Gone FC", "ar": "غون", "leagues": ["UAE Pro League"]},
       {"id": "3", "en": "Hellas", "ar": "", "leagues": ["Italian Serie A"]}]
new = [{"id": "1", "en": "Al-Ain", "ar": "العين", "leagues": ["Saudi-Arabian Pro League"]},
       {"id": "3", "en": "Hellas Verona", "ar": "هيلاس فيرونا", "leagues": ["Italian Serie A"]},
       {"id": "4", "en": "New FC", "ar": "نيو", "leagues": ["UAE Pro League"]}]
d = ti.diff(old, new)
check("diff: added, removed, renamed, moved", [t["id"] for t in d["added"]] == ["4"] and [t["id"] for t in d["removed"]] == ["2"]
      and [t["id"] for t in d["renamed"]] == ["3"] and [t["id"] for t in d["leagues changed"]] == ["1"], d)
md = ti.diff_md(d, len(old), len(new))
check("diff.md lists them", all(s in md for s in ("New FC", "Gone FC", "Hellas -> Hellas Verona", "Saudi-Arabian Pro League")), md)

print("\nall clubs collector checks passed" if not failed else f"\n{failed} failed")
sys.exit(1 if failed else 0)
