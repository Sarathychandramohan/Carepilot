"""Independent checks that the CarePilot dataset is REAL (generated or fetched, not written
by an LLM) and free of repetitions.  Place at backend/scripts/verify_real_data.py

  python -m backend.scripts.verify_real_data csv-overlap --demo synthea/carepilot_output/csv \
         --scale synthea/carepilot_output_2k/csv
  python -m backend.scripts.verify_real_data kb [--manifest data/manifests/kb_snapshot_v2.json]
  python -m backend.scripts.verify_real_data fda-check          # openFDA set_id vs raw JSON + EHR drug counts
  python -m backend.scripts.verify_real_data hash-anchor        # manifest raw_sha256 vs fetch-time reports
  python -m backend.scripts.verify_real_data pruning            # sections the HTML cleaner drops (is useful content lost?)
  python -m backend.scripts.verify_real_data db-dups            # needs backend/.env or PG* variables

Exit code is 1 when a hard failure is found, so scripts and agents cannot skip it.
Reports go to data/reports/.  Passwords are never printed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "reports"
MANIFESTS = ROOT / "data" / "manifests"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Only these hosts count as authoritative public sources. Extend deliberately, not silently.
ALLOWED_HOSTS = ("medlineplus.gov", "nlm.nih.gov", "nih.gov", "cdc.gov", "fda.gov",
                 "open.fda.gov", "api.fda.gov", "dailymed.nlm.nih.gov", "who.int", "nhs.uk")
SURROGATE_COLS = {"id", "stable_eid", "created_at", "updated_at", "loaded_at", "source_run", "is_demo_fixture"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ============================================================================ csv-overlap
def read_patients(csv_dir: Path):
    p = csv_dir / "patients.csv"
    if not p.exists():
        sys.exit(f"patients.csv not found in {csv_dir}")
    ids, finger, alive, dead = {}, {}, 0, 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            pid = r.get("Id") or r.get("ID") or r.get("id")
            ids[pid] = r
            fp = tuple((r.get(k) or "").strip().lower()
                       for k in ("BIRTHDATE", "GENDER", "FIRST", "LAST", "ADDRESS"))
            finger.setdefault(fp, pid)
            if (r.get("DEATHDATE") or "").strip():
                dead += 1
            else:
                alive += 1
    return ids, finger, alive, dead


def inventory(csv_dir: Path):
    inv = {}
    for f in sorted(csv_dir.glob("*.csv")):
        with open(f, encoding="utf-8", errors="replace", newline="") as fh:
            n = sum(1 for _ in fh) - 1
        inv[f.name] = {"rows": n, "sha256": sha256_file(f)}
    return inv


def rows_for_patients(csv_dir: Path, fname: str, patient_ids: set, key: str):
    """Count rows in fname whose patient key is in patient_ids."""
    p = csv_dir / fname
    if not p.exists():
        return 0
    n = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get(key) in patient_ids:
                n += 1
    return n


def cmd_csv_overlap(args) -> int:
    demo, scale = Path(args.demo), Path(args.scale)
    print("== Synthea source overlap (demo vs scale-up) ==")
    d_ids, d_fp, d_alive, d_dead = read_patients(demo)
    s_ids, s_fp, s_alive, s_dead = read_patients(scale)
    same_id = set(d_ids) & set(s_ids)
    same_fp = {fp: (d_fp[fp], s_fp[fp]) for fp in set(d_fp) & set(s_fp) if d_fp[fp] != s_fp[fp]}
    union = len(set(d_ids) | set(s_ids))
    print(f"  demo : {len(d_ids):>6,} patients (alive {d_alive:,}, deceased {d_dead:,})")
    print(f"  scale: {len(s_ids):>6,} patients (alive {s_alive:,}, deceased {s_dead:,})")
    print(f"  same patient Id in both runs      : {len(same_id):,}")
    print(f"  same demographics, different Id   : {len(same_fp):,}  (review manually; do not auto-merge)")
    print(f"  expected unique patients after merge: {union:,}")

    expected, inv_d, inv_s = {}, inventory(demo), inventory(scale)
    skip = same_id
    for fname in sorted(set(inv_d) | set(inv_s)):
        key = "Id" if fname == "patients.csv" else "PATIENT"
        s_rows = inv_s.get(fname, {}).get("rows", 0)
        d_rows = inv_d.get(fname, {}).get("rows", 0)
        dup_rows = rows_for_patients(demo, fname, skip, key) if skip and fname in inv_d else 0
        expected[fname] = {"scale_rows": s_rows, "demo_rows": d_rows,
                           "demo_rows_for_shared_patients_to_skip": dup_rows,
                           "expected_rows_after_merge": s_rows + d_rows - dup_rows}
    print("  expected rows after merge (patient-level dedupe, no row-level dropping):")
    for k, v in expected.items():
        print(f"    {k:26s} {v['expected_rows_after_merge']:>10,}")

    MANIFESTS.mkdir(parents=True, exist_ok=True)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "demo_dir": str(demo), "scale_dir": str(scale),
           "demo_files": inv_d, "scale_files": inv_s, "shared_patient_ids": len(same_id),
           "same_demographics_different_id": len(same_fp), "expected_unique_patients": union,
           "expected_rows_after_merge": expected}
    path = MANIFESTS / "ehr_source_manifest.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  wrote {path}  (SHA-256 of every source CSV: proof the files are unmodified)")
    print("  Use these expected counts to check the final database after the merge.")
    return 0


# ============================================================================ kb
def tokens(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(toks, n=5):
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def strip_markup(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s)
    return s


def index_files(folder: Path):
    idx = {}
    if folder.exists():
        for f in folder.rglob("*"):
            if f.is_file():
                for m in re.findall(r"KB-[A-Za-z0-9]+", f.stem):
                    idx.setdefault(m, f)
                idx.setdefault(f.stem, f)
    return idx


def first_of(d, keys, default=""):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


def host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def minhash_sigs(shingle_sets, k=16):
    try:
        import numpy as np
    except ImportError:
        return None
    rng = np.random.RandomState(7)
    a = rng.randint(1, 2**31 - 1, size=k).astype(np.uint64)
    b = rng.randint(0, 2**31 - 1, size=k).astype(np.uint64)
    p = np.uint64(2**31 - 1)
    sigs = np.full((len(shingle_sets), k), np.iinfo(np.uint64).max, dtype=np.uint64)
    for i, s in enumerate(shingle_sets):
        if not s:
            continue
        h = np.array([zlib.crc32(x.encode()) for x in s], dtype=np.uint64)
        sigs[i] = ((h[:, None] * a[None, :] + b[None, :]) % p).min(axis=0)
    return sigs


HEADER_LINE = re.compile(r"^\s*(#{1,6}\s|\*\*[A-Za-z0-9 _/-]+:\*\*|-{10,}\s*$|CHUNK \d+)")


def body_text(text: str) -> str:
    """Drop structural lines (markdown headings, '**Source:**' style metadata, chunk banners).
    Everything else must be traceable to the raw page."""
    return "\n".join(l for l in text.splitlines() if not HEADER_LINE.match(l))


def raw_text(p: Path) -> str:
    s = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json":
        try:
            obj = json.loads(s)
        except ValueError:
            return s
        out = []

        def walk(x):
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(obj)
        return "\n".join(out)
    return html.unescape(strip_markup(s))


def load_raw_hashes(paths):
    """doc_id -> raw-file SHA-256 recorded at fetch/ingest time (from fetch reports / provenance files)."""
    found = {}

    def walk(x):
        if isinstance(x, dict):
            did, h = x.get("doc_id"), x.get("raw_sha256") or x.get("sha256")
            if did and h and did not in found:
                found[did] = h
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for p in paths:
        if p.exists():
            try:
                walk(json.loads(p.read_text(encoding="utf-8-sig")))
            except ValueError:
                pass
    return found


def cmd_kb(args) -> int:
    print("== KB provenance and hallucination check ==")
    mpath = Path(args.manifest) if args.manifest else MANIFESTS / "kb_snapshot_v2.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    docs = m.get("documents", [])
    raw_idx = index_files(Path(args.raw) if args.raw else ROOT / "rag_knowledge" / "raw")
    clean_idx = index_files(Path(args.cleaned) if args.cleaned else ROOT / "rag_knowledge" / "cleaned")
    hash_files = [Path(x) for x in (args.raw_hashes or [])] or [
        MANIFESTS / "kb_raw_fetch_report.json", MANIFESTS / "openfda_ingest_provenance.json"]
    fetch_hashes = load_raw_hashes(hash_files)
    print(f"  manifest {mpath.name}: {len(docs)} documents; raw files indexed: {len(raw_idx)}; "
          f"cleaned: {len(clean_idx)}; fetch-time raw hashes found for {len(fetch_hashes)} docs")

    rows, issues = [], Counter()
    n_contain = n_rawsha = n_clean = 0
    sh_sets, titles_seen, text_hash_seen = [], defaultdict(list), defaultdict(list)
    for d in docs:
        did = str(first_of(d, ["doc_id", "id"]))
        title = str(first_of(d, ["title", "name"]))
        url = str(first_of(d, ["url", "source_url"]))
        lic = str(first_of(d, ["license", "licence"]))
        flags = []
        raw_p, clean_p = raw_idx.get(did), clean_idx.get(did)
        if not url:
            flags.append("NO_URL")
        elif not host_ok(url):
            flags.append("URL_HOST_NOT_ALLOWLISTED")
        if not lic:
            flags.append("NO_LICENSE")
        if not raw_p:
            flags.append("NO_RAW_FILE")
        if not clean_p:
            flags.append("NO_CLEANED_FILE")
        # raw hash recorded at fetch time must match the raw file on disk now
        expected = d.get("raw_sha256") or fetch_hashes.get(did)
        if raw_p:
            if not expected:
                flags.append("NO_RAW_SHA")
            else:
                n_rawsha += 1
                if expected != sha256_file(raw_p):
                    flags.append("RAW_SHA_MISMATCH")
        contain, strict = "", ""
        sset = set()
        if clean_p:
            n_clean += 1
            cbytes = clean_p.read_bytes()
            ctext = cbytes.decode("utf-8", errors="replace")
            text_hash_seen[hashlib.sha256(cbytes).hexdigest()].append(did)
            if d.get("text_sha256") and d["text_sha256"] != hashlib.sha256(cbytes).hexdigest():
                flags.append("TEXT_SHA_MISMATCH")
            sset = shingles(tokens(body_text(ctext)))
            if raw_p:
                rset = shingles(tokens(raw_text(raw_p)))
                if sset:
                    n_contain += 1
                    contain = len(sset & rset) / len(sset)
                    full = shingles(tokens(ctext))
                    strict = len(full & rset) / len(full) if full else ""
                    if contain < args.min_containment:
                        flags.append("TEXT_NOT_TRACEABLE_TO_RAW")
        titles_seen[re.sub(r"\W+", " ", title.lower()).strip()].append(did)
        sh_sets.append(sset)
        for f in flags:
            issues[f] += 1
        rows.append([did, title, url, lic, f"{contain:.3f}" if contain != "" else "",
                     f"{strict:.3f}" if strict != "" else "", ";".join(flags)])

    dup_title = {t: v for t, v in titles_seen.items() if len(v) > 1 and t}
    dup_sha = {s: v for s, v in text_hash_seen.items() if len(v) > 1}
    near = []
    sigs = minhash_sigs(sh_sets)
    if sigs is None:
        print("  [skip] numpy missing: near-duplicate check skipped")
    else:
        import numpy as np
        for i in range(len(docs)):
            if not sh_sets[i]:
                continue
            est = (sigs == sigs[i]).mean(axis=1)
            for j in np.where(est >= args.near_dup)[0]:
                if j > i and sh_sets[j]:
                    inter = len(sh_sets[i] & sh_sets[j])
                    jac = inter / max(1, len(sh_sets[i] | sh_sets[j]))
                    if jac >= args.near_dup:
                        near.append((rows[i][0], rows[j][0], round(jac, 3)))

    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(REPORTS / "real_data_kb_check.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_id", "title", "url", "license", "body_traceable_to_raw",
                    "strict_traceable_to_raw", "flags"])
        w.writerows(rows)
    hard = ["NO_URL", "URL_HOST_NOT_ALLOWLISTED", "NO_LICENSE", "NO_RAW_FILE", "NO_RAW_SHA",
            "RAW_SHA_MISMATCH", "TEXT_SHA_MISMATCH", "TEXT_NOT_TRACEABLE_TO_RAW"]
    checked = {"TEXT_NOT_TRACEABLE_TO_RAW": n_contain, "RAW_SHA_MISMATCH": n_rawsha}
    print("  issue counts (a zero only counts as a pass if the check actually ran; see 'checked on'):")
    for k in hard + ["NO_CLEANED_FILE"]:
        extra = f"   (checked on {checked[k]} of {len(docs)} docs)" if k in checked else ""
        print(f"    {k:28s} {issues[k]:>5}{extra}")
    print(f"    exact duplicate texts            {len(dup_sha):>5}")
    print(f"    duplicate titles                 {len(dup_title):>5}")
    for t, ids in list(dup_title.items())[:10]:
        print(f"      '{t}': {', '.join(ids)}")
    print(f"    near-duplicate pairs (>= {args.near_dup})  {len(near):>5}   (computed on {n_clean} docs with KB text)")
    for a_, b_, jac in near[:15]:
        print(f"      {a_} ~ {b_}  jaccard={jac}")
    if n_contain < len(docs) or n_rawsha < len(docs):
        print(f"  WARNING: traceability checked for {n_contain} docs, fetch-time raw hash for {n_rawsha} of {len(docs)}.")
    vals = [float(r[4]) for r in rows if r[4] != ""]
    if vals:
        print(f"  body containment: mean={sum(vals)/len(vals):.3f} min={min(vals):.3f}; "
              f">=0.95: {sum(v >= 0.95 for v in vals)}  <0.80: {sum(v < 0.80 for v in vals)}")
    bad = [r for r in rows if r[6]]
    print(f"  documents with at least one flag: {len(bad)} of {len(rows)}  -> {REPORTS / 'real_data_kb_check.csv'}")
    fail = sum(issues[k] for k in hard) + len(dup_sha)
    print("  RESULT:", "FAIL (fix or remove flagged documents)" if fail else "PASS")
    return 1 if fail else 0


# ============================================================================ fda-check
def cmd_fda_check(args) -> int:
    """openFDA documents: manifest set_id/effective_time must equal the raw JSON; drug-to-EHR counts
    are computed from medications.csv (never typed by hand)."""
    print("== openFDA documents: raw JSON vs manifest, and EHR medication counts ==")
    mpath = Path(args.manifest) if args.manifest else MANIFESTS / "kb_snapshot_v3.json"
    docs = [d for d in json.loads(mpath.read_text(encoding="utf-8")).get("documents", [])
            if str(first_of(d, ["doc_id", "id"])).upper().startswith("KB-FDA")]
    raw_idx = index_files(Path(args.raw) if args.raw else ROOT / "rag_knowledge" / "raw")
    meds = Path(args.meds) if args.meds else ROOT / "synthea" / "carepilot_output_2k" / "csv" / "medications.csv"
    desc_counts, total_rows = Counter(), 0
    if meds.exists():
        with open(meds, encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                total_rows += 1
                desc_counts[(r.get("DESCRIPTION") or "").lower()] += 1
    else:
        print(f"  medications.csv not found: {meds} (EHR counts skipped)")
    rows, bad, in_ehr, tails = [], 0, 0, defaultdict(list)
    matched_total = 0
    for d in docs:
        did = str(first_of(d, ["doc_id", "id"]))
        drug = re.sub(r"\s+Drug Information$", "", str(first_of(d, ["title", "name"]))).strip()
        raw_p = raw_idx.get(did)
        m_set, m_eff = str(d.get("set_id", "")), str(d.get("effective_time", ""))
        r_set = r_eff = ""
        status_ = "ok"
        if not raw_p or raw_p.suffix.lower() != ".json":
            status_ = "NO_RAW_JSON"
        else:
            try:
                res = json.loads(raw_p.read_text(encoding="utf-8")).get("results", [{}])[0]
                r_set, r_eff = str(res.get("set_id", "")), str(res.get("effective_time", ""))
            except (ValueError, IndexError, AttributeError):
                status_ = "RAW_JSON_UNREADABLE"
            if status_ == "ok" and (r_set != m_set or r_eff != m_eff):
                status_ = "MANIFEST_MISMATCH"
        bad += status_ != "ok"
        if m_set:
            tails[m_set.split("-")[-1]].append(did)
        n = sum(c for desc, c in desc_counts.items() if drug.lower() in desc) if desc_counts else ""
        if n:
            in_ehr += 1
            matched_total += n
        rows.append([did, drug, m_set, r_set, m_eff, r_eff, n, status_])
    sus = {t: v for t, v in tails.items() if len(v) > 1}
    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(REPORTS / "fda_ehr_check.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_id", "drug", "manifest_set_id", "raw_set_id", "manifest_effective", "raw_effective",
                    "ehr_medication_rows", "status"])
        w.writerows(rows)
    print(f"  openFDA documents: {len(docs)}; manifest != raw JSON or raw missing: {bad}")
    if desc_counts:
        print(f"  drugs with >= 1 EHR medication row: {in_ehr} of {len(docs)}; "
              f"matched rows {matched_total:,} (file has {total_rows:,} rows; a drug may match several rows)")
        if matched_total > total_rows:
            print("  NOTE: matched rows exceed file rows only if descriptions match several drug names; check overlaps")
    print(f"  set_ids sharing the same last 12 hex digits (almost never happens in real UUIDs): {len(sus)}")
    for t, v in list(sus.items())[:10]:
        print(f"    {t}: {', '.join(v)}")
    print(f"  wrote {REPORTS / 'fda_ehr_check.csv'}")
    fail = bad + len(sus)
    print("  RESULT:", "FAIL" if fail else "PASS")
    return 1 if fail else 0


# ============================================================================ hash-anchor
def cmd_hash_anchor(args) -> int:
    """Is the manifest's raw_sha256 really the hash recorded at fetch time (not recomputed later)?"""
    print("== raw hash anchor: manifest vs fetch-time reports ==")
    mpath = Path(args.manifest) if args.manifest else MANIFESTS / "kb_snapshot_v4.json"
    docs = json.loads(mpath.read_text(encoding="utf-8")).get("documents", [])
    files = [Path(x) for x in (args.reports or [])] or [
        MANIFESTS / "kb_raw_fetch_report.json", MANIFESTS / "openfda_ingest_provenance.json"]
    anchors = defaultdict(set)

    def walk(x, key_doc=None):
        if isinstance(x, dict):
            did = x.get("doc_id") or key_doc
            for k, v in x.items():
                if isinstance(v, str) and "sha" in k.lower() and len(v) == 64 and did:
                    anchors[did].add(v)
            for k, v in x.items():
                walk(v, k if isinstance(k, str) and k.upper().startswith("KB-") else did if x.get("doc_id") else None)
        elif isinstance(x, list):
            for v in x:
                walk(v, None)
    used = []
    for f in files:
        if f.exists():
            used.append(f.name)
            try:
                walk(json.loads(f.read_text(encoding="utf-8-sig")))
            except ValueError:
                print(f"  cannot parse {f}")
    match = mismatch = missing = 0
    bad = []
    for d in docs:
        did = str(first_of(d, ["doc_id", "id"]))
        mh = d.get("raw_sha256")
        if not anchors.get(did) or not mh:
            missing += 1
        elif mh in anchors[did]:
            match += 1
        else:
            mismatch += 1
            bad.append(did)
    print(f"  reports read: {used}; documents with a recorded fetch-time hash: {len(anchors)}")
    print(f"  manifest raw_sha256 equals a fetch-time hash : {match}")
    print(f"  manifest raw_sha256 DIFFERS from fetch report : {mismatch} {bad[:10]}")
    print(f"  no fetch-time hash to compare / manifest empty : {missing}")
    ok = mismatch == 0 and missing == 0
    print("  RESULT:", "PASS" if ok else "FAIL (raw_sha256 cannot be proven to come from fetch time)")
    return 0 if ok else 1


# ============================================================================ pruning
PRUNE_MARKERS = ["related topics", "latest news", "research", "journal articles", "clinical trials",
                 "find an expert", "patient handouts", "reference", "topic resources", "for you"]
KEEP_HINTS = ["result", "normal", "range", "dose", "dosage", "symptom", "risk", "treatment", "side effect"]


def cmd_pruning(args) -> int:
    """Which raw HTML sections does the cleaner's heading filter remove, and are any clinically useful?"""
    print("== sections removed by heading filter (raw HTML) ==")
    raw_dir = Path(args.raw) if args.raw else ROOT / "rag_knowledge" / "raw"
    seen = defaultdict(lambda: [0, 0])
    suspicious = []
    for f in sorted(raw_dir.glob("*.htm*")):
        t = f.read_text(encoding="utf-8", errors="replace")
        parts = re.split(r"(?is)<h[1-4][^>]*>(.*?)</h[1-4]>", t)
        # parts: [pre, heading1, body1, heading2, body2, ...]
        for i in range(1, len(parts) - 1, 2):
            head = html.unescape(re.sub(r"<[^>]+>", " ", parts[i]))
            head = re.sub(r"\s+", " ", head).strip().lower()
            body = re.sub(r"\s+", " ", html.unescape(strip_markup(parts[i + 1]))).strip()
            if any(re.search(m, head) for m in PRUNE_MARKERS):
                seen[head][0] += 1
                seen[head][1] += len(body)
                if any(h in head for h in KEEP_HINTS) and len(body) > 200:
                    suspicious.append((f.stem, head, len(body)))
    rows = sorted(seen.items(), key=lambda kv: -kv[1][0])
    print(f"  distinct removed heading texts: {len(rows)}")
    for head, (n, chars) in rows[: args.top]:
        print(f"    {n:>4} sections  avg {chars // max(1, n):>6} chars  '{head[:70]}'")
    REPORTS.mkdir(parents=True, exist_ok=True)
    with open(REPORTS / "kb_pruned_sections.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["heading", "sections", "avg_chars"])
        for head, (n, chars) in rows:
            w.writerow([head, n, chars // max(1, n)])
    print(f"  headings that look clinically useful (contain result/normal/range/dose/symptom/risk/treatment): {len(suspicious)}")
    for doc, head, n in suspicious[:20]:
        print(f"    {doc}: '{head[:60]}' ({n} chars removed)")
    print(f"  wrote {REPORTS / 'kb_pruned_sections.csv'}")
    print("  Review: if useful sections appear above, the cleaner is removing real content (the verifier cannot see this).")
    return 0


# ============================================================================ db-dups
def read_env(p: Path) -> dict:
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cmd_db_dups(args) -> int:
    print("== Database duplicate check ==")
    try:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
    except ImportError:
        print('  psycopg missing: pip install "psycopg[binary]"')
        return 1
    env = {**read_env(ROOT / ".env"), **read_env(ROOT / "backend" / ".env"), **os.environ}
    if args.dsn:
        dsn = args.dsn
    elif env.get("DATABASE_URL"):
        dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", env["DATABASE_URL"])
    else:
        dsn = make_conninfo(host=env.get("PGHOST", "localhost"), port=env.get("PGPORT", "5432"),
                            user=env.get("PGUSER", "postgres"), password=env.get("PGPASSWORD", ""),
                            dbname=env.get("PGDATABASE", "carepilot_db"))
    try:
        conn = psycopg.connect(dsn, connect_timeout=8)
    except Exception as exc:  # noqa: BLE001
        print("  cannot connect:", str(exc).splitlines()[0])
        return 1
    fails = 0
    with conn, conn.cursor() as cur:
        cur.execute("select table_name from information_schema.tables where table_schema=%s "
                    "and table_type='BASE TABLE' order by 1", (args.schema,))
        for (t,) in cur.fetchall():
            cur.execute("select column_name from information_schema.columns where table_schema=%s "
                        "and table_name=%s order by ordinal_position", (args.schema, t))
            cols = [c for (c,) in cur.fetchall() if c.lower() not in SURROGATE_COLS]
            if not cols:
                continue
            ident = sql.Identifier(args.schema, t)
            cur.execute(sql.SQL("select count(*) from {}").format(ident))
            n = cur.fetchone()[0]
            q = sql.SQL("select coalesce(sum(c-1),0) from (select count(*) c from {} group by {} "
                        "having count(*)>1) x").format(ident, sql.SQL(", ").join(map(sql.Identifier, cols)))
            cur.execute(q)
            dups = int(cur.fetchone()[0])
            fails += dups > 0
            print(f"  {t:28s} rows={n:>10,}  identical-row repeats={dups:>8,}  {'FAIL' if dups else 'ok'}")
            if t in ("patients", "patient"):
                for idc in ("id", "synthea_id", "patient_id", "source_id"):
                    if idc in [c.lower() for c in _all_cols(cur, args.schema, t)]:
                        cur.execute(sql.SQL("select count(*) - count(distinct {}) from {}")
                                    .format(sql.Identifier(idc), ident))
                        d = cur.fetchone()[0]
                        fails += d > 0
                        print(f"    duplicate {idc} values in {t}: {d}  {'FAIL' if d else 'ok'}")
    print("  note: identical-row repeats ignore surrogate columns (id, stable_eid, source_run, ...).")
    print("  RESULT:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


def _all_cols(cur, schema, table):
    cur.execute("select column_name from information_schema.columns where table_schema=%s and table_name=%s",
                (schema, table))
    return [c for (c,) in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("csv-overlap")
    a.add_argument("--demo", required=True)
    a.add_argument("--scale", required=True)
    k = sp.add_parser("kb")
    k.add_argument("--manifest")
    k.add_argument("--raw")
    k.add_argument("--cleaned")
    k.add_argument("--min-containment", type=float, default=0.95)
    k.add_argument("--near-dup", type=float, default=0.8)
    k.add_argument("--raw-hashes", nargs="*", default=None,
                   help="JSON files holding fetch-time raw hashes (default: kb_raw_fetch_report.json, openfda_ingest_provenance.json)")
    f = sp.add_parser("fda-check")
    f.add_argument("--manifest")
    f.add_argument("--raw")
    f.add_argument("--meds")
    h = sp.add_parser("hash-anchor")
    h.add_argument("--manifest")
    h.add_argument("--reports", nargs="*", default=None)
    pr = sp.add_parser("pruning")
    pr.add_argument("--raw")
    pr.add_argument("--top", type=int, default=25)
    d = sp.add_parser("db-dups")
    d.add_argument("--dsn")
    d.add_argument("--schema", default="public")
    args = ap.parse_args()
    code = {"csv-overlap": cmd_csv_overlap, "kb": cmd_kb, "fda-check": cmd_fda_check,
            "hash-anchor": cmd_hash_anchor, "pruning": cmd_pruning,
            "db-dups": cmd_db_dups}[args.cmd](args)
    sys.exit(code)


if __name__ == "__main__":
    main()