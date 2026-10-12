"""Pillar A inspection tool for CarePilot AI.

Place at: backend/scripts/inspect_pillar_a.py  (project root is two levels up)

Commands (run from the project root, using your venv):
  python -m backend.scripts.inspect_pillar_a kb         # list ALL KB documents -> CSV + HTML
  python -m backend.scripts.inspect_pillar_a db         # database report -> HTML (needs Postgres creds)
  python -m backend.scripts.inspect_pillar_a coverage   # which EHR concepts have no KB document
  python -m backend.scripts.inspect_pillar_a all

Outputs go to data/reports/. The database password is never printed. Credentials are
read from environment variables or backend/.env (DATABASE_URL, or DB_*/POSTGRES_*/PG*).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "reports"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------------------- html helpers
CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:24px;color:#1b1b1b}
h1{font-size:22px} h2{font-size:17px;margin-top:28px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 20px}
th,td{border:1px solid #d6d6d6;padding:5px 8px;text-align:left;vertical-align:top}
th{background:#f2f2f2;cursor:pointer;position:sticky;top:0}
tr:nth-child(even){background:#fafafa}
.warn{color:#9a5b00;font-weight:600} .ok{color:#17692d;font-weight:600} .bad{color:#a11;font-weight:600}
input{padding:6px 10px;width:340px;margin:8px 0} code{background:#f2f2f2;padding:1px 4px}
details{margin:6px 0} summary{cursor:pointer;font-weight:600}
"""
JS = """
function filt(inp,id){var q=inp.value.toLowerCase();
 document.querySelectorAll('#'+id+' tbody tr').forEach(function(r){
  r.style.display=r.textContent.toLowerCase().indexOf(q)>-1?'':'none';});}
document.querySelectorAll('th').forEach(function(th){th.addEventListener('click',function(){
 var t=th.closest('table'),b=t.tBodies[0],i=Array.from(th.parentNode.children).indexOf(th),
 asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
 var rows=Array.from(b.rows);rows.sort(function(x,y){
  var a=x.cells[i].textContent.trim(),c=y.cells[i].textContent.trim(),
  na=parseFloat(a.replace(/,/g,'')),nc=parseFloat(c.replace(/,/g,''));
  var r=(!isNaN(na)&&!isNaN(nc))?na-nc:a.localeCompare(c);return asc?r:-r;});
 rows.forEach(function(r){b.appendChild(r);});});});
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def cell(c) -> str:
    s = "" if c is None else str(c)
    if s.startswith("http://") or s.startswith("https://"):
        return f'<a href="{html.escape(s)}" target="_blank" rel="noopener">link</a>'
    return esc(s)


def table_html(headers, rows, table_id, filterable=True) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>" for r in rows)
    box = (f'<input placeholder="filter rows..." oninput="filt(this,\'{table_id}\')">'
           if filterable else "")
    return f'{box}<table id="{table_id}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def write_page(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>"
        f"<style>{CSS}</style></head><body><h1>{esc(title)}</h1>{body}<script>{JS}</script></body></html>",
        encoding="utf-8",
    )


def status(level: str, text: str) -> str:
    return f'<p class="{level}">{esc(text)}</p>'


# ----------------------------------------------------------------------------- KB inventory
def first_of(d: dict, keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def infer_source(doc_id: str) -> str:
    u = doc_id.upper()
    if u.startswith("KB-MP"):
        return "MedlinePlus (inferred from id)"
    if u.startswith("KB-FDA"):
        return "openFDA drug label (inferred from id)"
    return "core set / other (inferred from id)"


def chunk_stats(collection_name: str):
    """Return (per_doc_chunks, per_doc_chars, per_doc_first_text, total) from ChromaDB, or None."""
    try:
        import chromadb
    except ImportError:
        print("  [skip] chromadb not importable; chunk statistics unavailable")
        return None
    path = ROOT / "rag_knowledge" / "chroma_db"
    try:
        col = chromadb.PersistentClient(path=str(path)).get_collection(collection_name)
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] cannot open collection '{collection_name}': {exc}")
        return None
    total = col.count()
    chunks, chars, first, texts = Counter(), Counter(), {}, defaultdict(list)
    offset, batch = 0, 1000
    while offset < total:
        res = col.get(limit=batch, offset=offset, include=["documents", "metadatas"])
        for cid, text, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            doc_id = (meta or {}).get("doc_id")
            if not doc_id:
                parts = cid.split(":")
                doc_id = parts[1] if len(parts) > 1 else cid
            chunks[doc_id] += 1
            chars[doc_id] += len(text or "")
            first.setdefault(doc_id, (text or "")[:220].replace("\n", " "))
            texts[doc_id].append(text or "")
        offset += batch
    return chunks, chars, first, total, texts


def cmd_kb(args) -> dict | None:
    print("== KB inventory ==")
    mpath = ROOT / "data" / "manifests" / "kb_snapshot_v2.json"
    if not mpath.exists():
        print(f"  manifest not found: {mpath}")
        return None
    m = json.loads(mpath.read_text(encoding="utf-8"))
    docs = m.get("documents", [])
    print(f"  manifest: docs={m.get('doc_count')} chunks={m.get('chunk_count')} frozen={m.get('frozen')}")
    if docs:
        print(f"  document fields present: {sorted(docs[0].keys())}")

    stats = chunk_stats(args.collection)
    chunks, chars, first, total, texts = stats if stats else ({}, {}, {}, 0, {})
    if stats:
        print(f"  ChromaDB collection '{args.collection}': {total} chunks over {len(chunks)} docs")

    rows, titles, shas = [], Counter(), Counter()
    miss_lic = miss_url = miss_sha = thin = 0
    by_source = Counter()
    for d in docs:
        did = str(first_of(d, ["doc_id", "id"]))
        title = str(first_of(d, ["title", "name"]))
        src = str(first_of(d, ["source", "source_name", "publisher"])) or infer_source(did)
        url = str(first_of(d, ["url", "source_url"]))
        lic = str(first_of(d, ["license", "licence"]))
        sha = str(first_of(d, ["sha256", "hash", "content_hash"]))
        n = chunks.get(did, int(first_of(d, ["chunk_count", "chunks"], 0) or 0))
        ch = chars.get(did, 0)
        miss_lic += not lic
        miss_url += not url
        miss_sha += not sha
        thin += n <= 1
        titles[re.sub(r"\W+", " ", title.lower()).strip()] += 1
        if sha:
            shas[sha] += 1
        by_source[src] += 1
        rows.append([did, title, src, lic, url, sha[:12], n, ch, first.get(did, "")])
    dup_titles = sum(c - 1 for c in titles.values() if c > 1)
    dup_sha = sum(c - 1 for c in shas.values() if c > 1)

    REPORTS.mkdir(parents=True, exist_ok=True)
    headers = ["doc_id", "title", "source", "license", "url", "sha256(12)", "chunks", "chars", "starts with"]
    with open(REPORTS / "kb_inventory.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)

    body = [f"<p>Snapshot <code>{esc(m.get('snapshot_id', 'v2'))}</code>: "
            f"<b>{len(docs)}</b> documents, <b>{esc(total or m.get('chunk_count'))}</b> chunks.</p>"]
    body.append("<h2>Checks</h2>")
    body.append(status("ok" if len(docs) >= 500 else "bad",
                       f"Document floor (>= 500): {len(docs)}"))
    body.append(status("ok" if not miss_lic else "bad", f"Documents with no license recorded: {miss_lic}"))
    body.append(status("ok" if not miss_url else "warn", f"Documents with no URL: {miss_url}"))
    body.append(status("ok" if not miss_sha else "warn", f"Documents with no SHA-256: {miss_sha}"))
    body.append(status("warn" if dup_titles else "ok", f"Duplicate titles (possible near-duplicates): {dup_titles}"))
    body.append(status("warn" if dup_sha else "ok", f"Duplicate content hashes: {dup_sha}"))
    body.append(status("warn" if thin else "ok", f"Documents with 1 chunk or fewer (thin content): {thin}"))
    body.append("<h2>By source</h2>")
    body.append(table_html(["source", "documents"], sorted(by_source.items()), "t_src", False))
    body.append("<h2>All documents</h2>" + table_html(headers, rows, "t_docs"))
    write_page(REPORTS / "kb_inventory.html", "CarePilot KB inventory", "".join(body))

    print(f"  by source: {dict(by_source)}")
    print(f"  no license: {miss_lic} | no url: {miss_url} | no sha: {miss_sha} | "
          f"dup titles: {dup_titles} | dup hashes: {dup_sha} | thin docs: {thin}")
    print(f"  wrote {REPORTS / 'kb_inventory.csv'}")
    print(f"  wrote {REPORTS / 'kb_inventory.html'}  (open in a browser; click headers to sort)")
    return {"texts": texts, "docs": docs}


# ----------------------------------------------------------------------------- database report
def read_env_file(p: Path) -> dict:
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def conninfo(args) -> str:
    from psycopg.conninfo import make_conninfo
    if args.dsn:
        return args.dsn
    env = {**read_env_file(ROOT / ".env"), **read_env_file(ROOT / "backend" / ".env"), **os.environ}
    url = env.get("DATABASE_URL")
    if url:
        return re.sub(r"^postgresql\+\w+://", "postgresql://", url)

    def pick(*keys, default=None):
        for k in keys:
            if env.get(k):
                return env[k]
        return default

    return make_conninfo(
        host=pick("DB_HOST", "POSTGRES_HOST", "PGHOST", default="localhost"),
        port=pick("DB_PORT", "POSTGRES_PORT", "PGPORT", default="5432"),
        user=pick("DB_USER", "POSTGRES_USER", "PGUSER", default="postgres"),
        password=pick("DB_PASSWORD", "POSTGRES_PASSWORD", "PGPASSWORD", default=""),
        dbname=pick("DB_NAME", "POSTGRES_DB", "PGDATABASE", default="carepilot_db"),
    )


def short(v, n=70):
    s = "NULL" if v is None else str(v)
    return s if len(s) <= n else s[: n - 3] + "..."


def cmd_db(args) -> None:
    print("== Database report ==")
    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        print("  psycopg not installed: pip install \"psycopg[binary]\"")
        return
    try:
        conn = psycopg.connect(conninfo(args), connect_timeout=8)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0]
        print(f"  cannot connect: {msg}")
        print("  Put credentials in backend/.env (DATABASE_URL=...) or set PGPASSWORD, then re-run.")
        return

    body, checks = [], []
    with conn, conn.cursor() as cur:
        cur.execute("select current_database(), version()")
        dbname, ver = cur.fetchone()
        body.append(f"<p>Database <code>{esc(dbname)}</code> | {esc(ver.split(',')[0])}</p>")
        cur.execute("select table_name from information_schema.tables "
                    "where table_schema='public' and table_type='BASE TABLE' order by 1")
        tables = [r[0] for r in cur.fetchall()]
        summary, detail, table_info = [], [], {}
        for t in tables:
            ident = sql.Identifier(t)
            cur.execute(sql.SQL("select count(*) from {}").format(ident))
            n = cur.fetchone()[0]
            cur.execute("select pg_size_pretty(pg_total_relation_size(%s::regclass))", (f'public."{t}"',))
            size = cur.fetchone()[0]
            cur.execute("select column_name, data_type from information_schema.columns "
                        "where table_schema='public' and table_name=%s order by ordinal_position", (t,))
            cols = cur.fetchall()
            cur.execute("select indexname, indexdef from pg_indexes where schemaname='public' and tablename=%s", (t,))
            idx = cur.fetchall()
            cur.execute(sql.SQL("select * from {} limit 3").format(ident))
            sample = cur.fetchall()
            names = [c[0] for c in cols]
            table_info[t] = (n, names)
            summary.append([t, n, size, len(cols), len(idx)])
            inner = ["<p><b>Columns:</b> " + ", ".join(f"{esc(c)} <i>({esc(d)})</i>" for c, d in cols) + "</p>"]
            inner.append("<p><b>Indexes:</b></p>" + table_html(["name", "definition"], idx, f"i_{t}", False))
            inner.append("<p><b>Sample rows:</b></p>" + table_html(
                names, [[short(v) for v in r] for r in sample], f"s_{t}", False))
            detail.append(f"<details><summary>{esc(t)} ({n:,} rows)</summary>{''.join(inner)}</details>")
            print(f"  {t:28s} {n:>10,} rows  {size:>9s}  cols={len(cols)} indexes={len(idx)}")

        # ---- Pillar A checklist
        def count(t):
            return table_info.get(t, (None, []))[0]

        pat = next((t for t in ("patients", "patient") if t in table_info), None)
        if pat:
            n = count(pat)
            checks.append(("ok" if n >= 1000 else "bad", f"{pat}: {n:,} rows (floor 1,000; target 2,000 alive)"))
            death_cols = [c for c in table_info[pat][1] if "death" in c.lower()]
            if death_cols:
                dc = sql.Identifier(death_cols[0])
                cur.execute(sql.SQL("select count(*) filter (where {c} is null), "
                                    "count(*) filter (where {c} is not null) from {t}")
                            .format(c=dc, t=sql.Identifier(pat)))
                alive, dead = cur.fetchone()
                checks.append(("warn" if dead else "ok",
                               f"alive={alive:,} deceased={dead:,} (exclude deceased from patient accounts and queries)"))
        else:
            checks.append(("bad", "no patients table found"))
        for t, (n, names) in table_info.items():
            if "stable_eid" in names:
                cur.execute(sql.SQL("select count(*) from {} where stable_eid is null").format(sql.Identifier(t)))
                nulls = cur.fetchone()[0]
                checks.append(("ok" if nulls == 0 else "bad", f"{t}: stable_eid NULL in {nulls:,} rows"))
        for t in ("reference_ranges", "referencerange", "kb_documents", "kb_snapshots", "consultations", "users"):
            if t in table_info:
                checks.append(("ok" if table_info[t][0] else "warn", f"{t}: {table_info[t][0]:,} rows"))
            else:
                checks.append(("warn", f"{t}: table not present"))

    body.append("<h2>Pillar A checklist</h2>" + "".join(status(l, s) for l, s in checks))
    body.append("<h2>Tables</h2>" + table_html(["table", "rows", "size", "columns", "indexes"], summary, "t_tables", False))
    body.append("<h2>Table details</h2>" + "".join(detail))
    write_page(REPORTS / "db_report.html", "CarePilot database report", "".join(body))
    for l, s in checks:
        print(f"  [{l.upper():4s}] {s}")
    print(f"  wrote {REPORTS / 'db_report.html'}")


# ----------------------------------------------------------------------------- coverage
GENERIC = {"acute", "chronic", "essential", "primary", "secondary", "mild", "moderate", "severe",
           "finding", "history", "of", "the", "and", "in", "type", "mellitus", "disease", "disorder",
           "syndrome", "stage", "with", "without", "due", "to", "situation", "procedure"}


# Common medication delivery forms, units, packaging terms to ignore
MED_STOP_WORDS = {
    "pack", "tablet", "oral", "injection", "solution", "extended", "release",
    "ophthalmic", "suspension", "gel", "metered", "dose", "inhaler", "dry",
    "powder", "transdermal", "system", "implant", "vaginal", "usp", "inert",
    "ingredients", "actuat", "hr", "day", "chewable", "capsule", "cream",
    "injectable", "film", "patch", "spray", "mucosal", "mg", "ml", "mcg",
    "unt", "meq", "sodium", "chloride", "potassium", "sulfate", "tartrate",
    "maleate", "fumarate", "succinate", "hydrochloride", "acetate", "propionate",
    "valerate", "bitartrate", "phosphate", "bromide", "deterrent", "abuse"
}


def probe_for(desc: str, kind: str) -> str:
    """Short phrase used for a rough 'does the KB mention this?' match."""
    if kind == "lab":
        # Strip LOINC dimensional jargon in brackets, e.g. [Mass/volume], [#/volume], [Volume Fraction], [Presence], [Moles/volume], [Entitic mean volume]
        s = re.sub(r"\[.*?\]", " ", desc)
        # Also clean parentheticals and delimiters
        s = re.sub(r"\(.*?\)", " ", s)
        words = [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]
        s_lower = s.lower()
        if "hemoglobin a1c" in s_lower or "a1c" in s_lower:
            return "a1c"
        if "platelet distribution width" in s_lower:
            return "platelet"
        if "leukocyte esterase" in s_lower:
            return "leukocyte"
        LAB_SKIP = {"by", "automated", "count", "test", "strip", "microscopy", "light",
                    "high", "power", "field", "culture", "calculation", "sediment", "area"}
        clean_words = [w for w in words if w not in LAB_SKIP and not w.isdigit()]
        return clean_words[0] if clean_words else ""

    if kind == "medication":
        # Remove brand names in brackets e.g. [Jolivette 28 Day], [Flovent]
        s = re.sub(r"\[.*?\]", " ", desc)
        words = [w for w in re.split(r"[^A-Za-z]+", s.lower()) if w]
        candidate_words = [w for w in words if len(w) > 2 and w not in MED_STOP_WORDS and not w.isdigit()]
        return candidate_words[0] if candidate_words else ""

    s = re.sub(r"\(.*?\)", " ", desc)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]
    words = [w for w in words if w not in GENERIC and not w.isdigit()]
    return words[0] if words else ""


def cmd_coverage(args, kb_ctx=None) -> None:
    print("== KB coverage of EHR concepts ==")
    csv_dir = Path(args.synthea_csv) if args.synthea_csv else ROOT / "synthea" / "carepilot_output_2k" / "csv"
    if not csv_dir.exists():
        print(f"  Synthea CSV folder not found: {csv_dir}")
        return
    if kb_ctx is None:
        stats = chunk_stats(args.collection)
        texts = stats[4] if stats else {}
    else:
        texts = kb_ctx["texts"]
    # Check snapshot manifests in descending version order
    mpath = None
    for cand in ("kb_snapshot_v5.json", "kb_snapshot_v4.json", "kb_snapshot_v3.json", "kb_snapshot_v2.json"):
        p = ROOT / "data" / "manifests" / cand
        if p.exists():
            mpath = p
            break
    titles = {}
    if mpath and mpath.exists():
        for d in json.loads(mpath.read_text(encoding="utf-8")).get("documents", []):
            titles[str(first_of(d, ["doc_id", "id"]))] = str(first_of(d, ["title", "name"])).lower()
    if not texts and not titles:
        print("  no KB text or titles available")
        return
    corpus = {k: " ".join(v).lower() for k, v in texts.items()} if texts else {}
    title_blob = "\n".join(titles.values())
    text_blob = "\n".join(corpus.values())

    specs = [("conditions.csv", "condition", None), ("medications.csv", "medication", None),
             ("observations.csv", "lab", "laboratory")]
    rows, missing_by_kind = [], Counter()
    for fname, kind, category in specs:
        p = csv_dir / fname
        if not p.exists():
            print(f"  missing {fname}")
            continue
        rowc, pats = Counter(), defaultdict(set)
        with open(p, encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                if category and (r.get("CATEGORY") or "").lower() != category:
                    continue
                d = r.get("DESCRIPTION") or ""
                if d:
                    rowc[d] += 1
                    pats[d].add(r.get("PATIENT"))
        for desc, cnt in sorted(rowc.items(), key=lambda kv: -len(pats[kv[0]]))[: args.top]:
            probe = probe_for(desc, kind)
            in_title = bool(probe) and probe in title_blob
            in_text = bool(probe) and probe in text_blob
            level = "title" if in_title else "text-only" if in_text else "MISSING"
            missing_by_kind[(kind, level)] += 1
            rows.append([kind, desc, len(pats[desc]), cnt, probe, level])
    headers = ["kind", "EHR description", "patients", "rows", "search phrase", "KB coverage"]
    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(REPORTS / "kb_coverage.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)
    miss = [r for r in rows if r[5] == "MISSING"]
    body = ["<p>For the most common EHR concepts (by number of patients), does the KB mention them? "
            "This is a rough phrase match, not a clinical judgement: review the MISSING rows by hand "
            "and add documents for the ones that matter.</p>",
            status("warn" if miss else "ok", f"{len(miss)} of {len(rows)} top concepts have no KB mention"),
            table_html(headers, rows, "t_cov")]
    write_page(REPORTS / "kb_coverage.html", "KB coverage of EHR concepts", "".join(body))
    for k in ("condition", "medication", "lab"):
        t = {lv: missing_by_kind[(k, lv)] for lv in ("title", "text-only", "MISSING")}
        print(f"  {k:10s} {t}")
    print(f"  wrote {REPORTS / 'kb_coverage.csv'} and kb_coverage.html")


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["kb", "db", "coverage", "all"])
    ap.add_argument("--collection", default="carepilot_kb_v2")
    ap.add_argument("--dsn", default=None, help="Postgres connection string (otherwise .env / env vars)")
    ap.add_argument("--synthea-csv", default=None, help="folder with Synthea CSVs (default: 2k output)")
    ap.add_argument("--top", type=int, default=40, help="top-N concepts per kind for coverage")
    args = ap.parse_args()

    ctx = None
    if args.command in ("kb", "all"):
        ctx = cmd_kb(args)
    if args.command in ("db", "all"):
        cmd_db(args)
    if args.command in ("coverage", "all"):
        cmd_coverage(args, ctx)


if __name__ == "__main__":
    main()
