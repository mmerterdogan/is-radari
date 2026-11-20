"""Schema check for site/isealimci.json (recruiters tab).

The file is edited by hand and by the weekly cloud routine, so a broken
entry must fail CI before it reaches the live site. Runs without pytest too:
    python3 tests/test_isealimci.py
"""
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "site" / "isealimci.json"
PROFILE = re.compile(r"^https://www\.linkedin\.com/in/[^/?#\s]+/$")
ROLES = {"İşe alım", "Mühendis", "Yönetici"}


def load():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_top_level():
    d = load()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["updated"])
    assert isinstance(d["companies"], list) and d["companies"]
    for k in d.get("kuyruk", []):
        assert k["sirket"].strip()


def test_companies():
    d = load()
    ids, names = set(), set()
    for c in d["companies"]:
        assert c["id"] and c["id"] not in ids, c["id"]
        ids.add(c["id"])
        assert c["sirket"].strip() and c["sirket"].lower() not in names, c["sirket"]
        names.add(c["sirket"].lower())
        re.compile(c.get("match") or c["sirket"])  # site builds a RegExp from this
        assert isinstance(c.get("kisiler", []), list)


def test_people():
    seen = set()
    for c in load()["companies"]:
        for p in c.get("kisiler", []):
            assert p["ad"].strip(), c["sirket"]
            assert p["rol"] in ROLES, (p["ad"], p["rol"])
            assert PROFILE.match(p["linkedin"]), p["linkedin"]
            slug = p["linkedin"].lower()
            assert slug not in seen, f"duplicate person {p['ad']}"
            seen.add(slug)
            assert p.get("dogrulandi", True) in (True, False)
            # public repo: names, titles and public profile URLs only
            text = json.dumps({k: v for k, v in p.items() if k not in ("linkedin", "eklendi")}, ensure_ascii=False)
            assert not re.search(r"@|\+?\d[\d ()-]{9,}", text), p["ad"]


def test_mentors_and_academics():
    d = load()
    for p in d.get("mentorlar", []):
        assert p["ad"].strip() and p.get("kurum"), p
        assert PROFILE.match(p["linkedin"]), p["linkedin"]
    for p in d.get("hocalar", []):
        assert p["ad"].strip() and p.get("kurum"), p
        assert p["link"].startswith("https://"), p["link"]   # official university / group page
        assert p.get("ulke", "Türkiye") in ("Türkiye", "Yurt dışı")
    for c in d["companies"]:
        assert c.get("tur", "sirket") in ("sirket", "startup"), c["sirket"]


def test_queue_not_already_listed():
    d = load()
    listed = {c["sirket"].lower() for c in d["companies"]}
    for k in d.get("kuyruk", []):
        assert k["sirket"].lower() not in listed, k["sirket"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("isealimci.json OK")
