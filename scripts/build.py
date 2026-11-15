#!/usr/bin/env python3
"""Podcast « Conteur d'Afrique » : une histoire complète = un épisode.

Chaque jour : lit Notion (épisodes des contes et des héros, sujets Excellence), garde les histoires
dont TOUTES les parties sont déjà sorties sur les réseaux, assemble leurs parties dans l'ordre
(son des vidéos, carte de fin retirée entre deux parties), ajoute le MP3 dans docs/episodes/
et régénère docs/feed.xml. Rien n'est jamais mélangé : un épisode ne contient qu'une seule histoire.
Variable d'environnement : NOTION_TOKEN.
"""
import json, os, re, unicodedata, subprocess, sys, tempfile, urllib.request, datetime, html, hashlib
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs"); EPDIR = os.path.join(DOCS, "episodes")
CONF = json.load(open(os.path.join(ROOT, "podcast.json")))
REG = os.path.join(ROOT, "episodes.json")
TOKEN = os.environ["NOTION_TOKEN"]
H = {"Authorization": TOKEN if TOKEN.startswith("Bearer") else "Bearer " + TOKEN, "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
PARIS = ZoneInfo("Europe/Paris")
END_CARD = 4.0
MAX_PAR_PASSAGE = int(os.environ.get("MAX_EPISODES", "3"))

def notion(path, body=None):
    r = urllib.request.Request("https://api.notion.com/v1/" + path, data=json.dumps(body).encode() if body is not None else None,
                               headers=H, method="POST" if body is not None else "GET")
    return json.load(urllib.request.urlopen(r, timeout=60))

def query(db, filt):
    out, cur = [], None
    while True:
        b = {"page_size": 100, "filter": filt}
        if cur: b["start_cursor"] = cur
        r = notion(f"databases/{db}/query", b); out += r["results"]
        if not r.get("has_more"): return out
        cur = r["next_cursor"]

txt = lambda p: "".join(x["plain_text"] for x in (p.get("title") or p.get("rich_text") or []))
sel = lambda p: (p.get("select") or {}).get("name", "")

def date_diffusion(props, edited):
    ms = re.findall(r"(?:pour le|même créneau) (\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d)", txt(props.get("Logs", {})))
    m = ms[-1] if ms else None   # la dernière programmation du journal fait foi
    if m:
        d, mo, y, h, mi = map(int, m)
        return datetime.datetime(y, mo, d, h, mi, tzinfo=PARIS)
    # pas de date dans le journal : on attend un jour après la dernière modification
    return datetime.datetime.fromisoformat(edited.replace("Z", "+00:00")) + datetime.timedelta(days=1)

def histoires():
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    # contes et héros : regroupés par conte, toutes les parties 1..N, la dernière déjà diffusée
    pages = query(CONF["notion_episodes"], {"or": [{"property": "Statut", "select": {"equals": s}} for s in ("Programmé", "Publié")]})
    groupes = {}
    for p in pages:
        P = p["properties"]; rel = (P["Conte"]["relation"] or [{}])[0].get("id")
        if not rel or not P["Vidéo (MP4)"]["url"]: continue
        groupes.setdefault(rel, []).append(p)
    for rel, eps in groupes.items():
        eps.sort(key=lambda e: e["properties"]["Numéro"]["number"] or 0)
        sur = max(e["properties"]["Sur"]["number"] or 1 for e in eps)
        nums = [e["properties"]["Numéro"]["number"] for e in eps]
        if sorted(set(nums)) != list(range(1, sur + 1)): continue
        eps = [next(e for e in eps if e["properties"]["Numéro"]["number"] == n) for n in range(1, sur + 1)]
        if max(date_diffusion(e["properties"], e["last_edited_time"]) for e in eps) > now: continue
        P0 = eps[0]["properties"]; titre0 = txt(P0["Titre"])
        serie = re.split(r"\s+—\s+\d+/\d+", titre0)[0].strip()
        parts = [re.sub(r"^.*?—\s*\d+/\d+\s*:\s*", "", txt(e["properties"]["Titre"])) for e in eps]
        try: script = json.loads(txt(eps[-1]["properties"]["Script"]))
        except Exception: script = {}
        source = (script.get("carte_source") or "").replace("\\N", "\n").split("\n")
        try: rub = "Héros" if sel(notion("pages/" + rel)["properties"].get("Type", {})) == "Héros" else "Conte"   # le catalogue fait foi
        except Exception: rub = sel(P0["Rubrique"]) or "Conte"
        if rub == "Héros": source = [re.sub(r"^Conte\s+", "Histoire vraie, ", source[0])] + source[1:] if source and source[0] else source
        desc = (f"{serie}.\n\n" + ("\n".join(f"Partie {i + 1} : {t}" for i, t in enumerate(parts)) + "\n\n" if sur > 1 else "")
                + " · ".join(s for s in source if s.strip()) + "\n\nConteur d'Afrique : contes, héros et histoire de l'Afrique, racontés en français.")
        out.append({"cle": "conte-" + rel, "titre": serie, "rubrique": rub, "description": desc.strip(),
                    "videos": [e["properties"]["Vidéo (MP4)"]["url"] for e in eps],
                    "date": max(date_diffusion(e["properties"], e["last_edited_time"]) for e in eps).isoformat()})
    # Excellence : une vidéo = une histoire ; une reprise du même sujet remplace la version précédente
    vus = {}
    for p in query(CONF["notion_excellence"], {"property": "Statut", "select": {"equals": "Programmé"}}):
        P = p["properties"]
        if not P["Vidéo (MP4)"]["url"]: continue
        d = date_diffusion(P, p["last_edited_time"])
        if d > now: continue
        h = {"cle": "excellence-" + p["id"], "titre": txt(P["Titre"]) or txt(P["Sujet"]), "rubrique": "Excellence",
             "description": (txt(P["Légende"]) + "\n\nExcellence africaine, une série de Conteur d'Afrique.").strip(),
             "videos": [P["Vidéo (MP4)"]["url"]], "date": d.isoformat()}
        sujet = re.split(r"\s*[,:—]", txt(P["Sujet"]) or h["titre"])[0].strip().lower()
        if sujet not in vus or vus[sujet]["date"] < h["date"]: vus[sujet] = h
    out += vus.values()
    return sorted(out, key=lambda h: h["date"])

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise SystemExit(" ".join(cmd[:4]) + "\n" + r.stderr[-800:])
    return r.stdout

def duree(f):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).strip())

def assembler(h, dest):
    with tempfile.TemporaryDirectory() as t:
        morceaux = []
        for i, url in enumerate(h["videos"]):
            v = os.path.join(t, f"{i}.mp4"); urllib.request.urlretrieve(url, v)
            d = duree(v); fin = d if i == len(h["videos"]) - 1 else max(1.0, d - END_CARD)
            a = os.path.join(t, f"{i}.wav")
            run(["ffmpeg", "-y", "-v", "error", "-i", v, "-vn", "-t", f"{fin:.2f}", "-ac", "1", "-ar", "44100", a])
            morceaux.append(a)
        silence = os.path.join(t, "s.wav")
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1.0", silence])
        liste = os.path.join(t, "l.txt")
        open(liste, "w").write("".join(f"file '{m}'\n" + (f"file '{silence}'\n" if k < len(morceaux) - 1 else "") for k, m in enumerate(morceaux)))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", liste, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k", "-id3v2_version", "3",
             "-metadata", f"title={h['titre']}", "-metadata", f"artist={CONF['auteur']}", "-metadata", f"album={CONF['titre']}", dest])

def feed(reg):
    base = CONF["url_site"].rstrip("/")
    def rfc(d): return datetime.datetime.fromisoformat(d).astimezone(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    e = html.escape
    items = []
    for x in sorted(reg, key=lambda r: r["date"], reverse=True):
        dur = int(round(x["duree"]))
        items.append(f"""    <item>
      <title>{e(x['titre'])}</title>
      <description>{e(x['description'])}</description>
      <itunes:summary>{e(x['description'])}</itunes:summary>
      <enclosure url="{base}/episodes/{x['fichier']}" length="{x['taille']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{e(x['cle'])}</guid>
      <pubDate>{rfc(x['date'])}</pubDate>
      <itunes:duration>{dur // 3600:02d}:{dur % 3600 // 60:02d}:{dur % 60:02d}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{e(CONF['titre'])}</title>
    <link>{base}/</link>
    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
    <language>fr</language>
    <description>{e(CONF['description'])}</description>
    <itunes:summary>{e(CONF['description'])}</itunes:summary>
    <itunes:author>{e(CONF['auteur'])}</itunes:author>
    <itunes:owner><itunes:name>{e(CONF['auteur'])}</itunes:name><itunes:email>{e(CONF['email'])}</itunes:email></itunes:owner>
    <itunes:image href="{base}/cover.jpg"/>
    <image><url>{base}/cover.jpg</url><title>{e(CONF['titre'])}</title><link>{base}/</link></image>
    <itunes:category text="{e(CONF['categorie'])}"><itunes:category text="{e(CONF['sous_categorie'])}"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""

def main():
    reg = json.load(open(REG)) if os.path.exists(REG) else []
    faits = {r["cle"] for r in reg}
    nouveaux = [h for h in histoires() if h["cle"] not in faits][:MAX_PAR_PASSAGE]
    for h in nouveaux:
        nom = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFD", h["titre"].lower()).encode("ascii", "ignore").decode()).strip("-")[:60] or "episode"
        fichier = f"{h['date'][:10]}-{nom}-{hashlib.sha1(h['cle'].encode()).hexdigest()[:6]}.mp3"
        dest = os.path.join(EPDIR, fichier)
        assembler(h, dest)
        reg.append({k: h[k] for k in ("cle", "titre", "rubrique", "description", "date")} | {"fichier": fichier, "taille": os.path.getsize(dest), "duree": duree(dest), "parties": len(h["videos"])})
        print(f"+ {h['rubrique']} : {h['titre']} ({len(h['videos'])} partie(s), {reg[-1]['duree']:.0f} s)")
    json.dump(reg, open(REG, "w"), ensure_ascii=False, indent=1)
    open(os.path.join(DOCS, "feed.xml"), "w").write(feed(reg))
    print(f"{len(nouveaux)} nouvel(s) épisode(s), {len(reg)} au total")

if __name__ == "__main__":
    main()
