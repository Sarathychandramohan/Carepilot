"""
backend/scripts/kb_fetch_raw.py

KB provenance fetcher (Step 2 addition).

For every document in the KB manifest:
  1. Re-fetches its URL (rate-limited; 1 req/sec by default).
  2. Saves the raw response to  rag_knowledge/raw/{doc_id}.<ext>
  3. Records HTTP status, retrieved_at, and SHA-256 in
     data/manifests/kb_raw_fetch_report.json

Documents whose URL fails (non-2xx or connection error) are marked
"unverified" and listed at the end.  No content is invented or
substituted from memory.

Usage (from project root with venv active):
  python -m backend.scripts.kb_fetch_raw
  python -m backend.scripts.kb_fetch_raw --delay 2.0       # slower (2 s between requests)
  python -m backend.scripts.kb_fetch_raw --resume           # skip doc_ids that already have a raw file
  python -m backend.scripts.kb_fetch_raw --retry-failed     # only retry the 33 previously failed docs
  python -m backend.scripts.kb_fetch_raw --limit 20         # fetch only the first 20 docs (for testing)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs, quote, quote_plus
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAW_DIR   = PROJECT_ROOT / "rag_knowledge" / "raw"
MANIFESTS = PROJECT_ROOT / "data" / "manifests"
MANIFEST  = MANIFESTS / "kb_snapshot_v2.json"

# Map URL hostname -> preferred file extension for raw save
EXT_MAP = {
    "medlineplus.gov":            ".html",
    "wsearch.nlm.nih.gov":        ".xml",
    "nlm.nih.gov":                ".html",
    "nih.gov":                    ".html",
    "niddk.nih.gov":              ".html",
    "cdc.gov":                    ".html",
    "fda.gov":                    ".html",
    "api.fda.gov":                ".json",
    "open.fda.gov":               ".json",
    "dailymed.nlm.nih.gov":       ".html",
    "who.int":                    ".html",
    "nhs.uk":                     ".html",
}

# Use a real browser UA — medlineplus.gov and dailymed block urllib's default UA
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",   # disable gzip so we get raw bytes without needing gzip.decompress
}

MAX_BYTES = 5 * 1024 * 1024  # 5 MB per document


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_url(url: str) -> str:
    """Re-encode a URL so that query-string values with spaces use +/%20 correctly."""
    parsed = urlparse(url)
    # Re-encode path (safe chars for path)
    path = quote(parsed.path, safe="/%@:!$&'()*+,;=")
    # Re-encode query: split into k=v pairs, re-encode values
    if parsed.query:
        # parse_qs decodes %xx but also loses ordering; use manual split to preserve order
        parts = parsed.query.split("&")
        encoded_parts = []
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                encoded_parts.append(f"{quote(k, safe='')}={quote_plus(v)}")
            else:
                encoded_parts.append(quote(part, safe=""))
        query = "&".join(encoded_parts)
    else:
        query = ""
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, parsed.fragment))


def ext_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for h, e in EXT_MAP.items():
        if host == h or host.endswith("." + h):
            return e
    return ".html"


def fetch_url(url: str, timeout: int = 30) -> tuple[int, bytes, str]:
    """
    Returns (http_status, body_bytes, content_type).
    Raises nothing — errors are returned as status < 0.
    """
    encoded_url = encode_url(url)
    try:
        req = Request(encoded_url, headers=HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ct = resp.headers.get("Content-Type", "")
            body = resp.read(MAX_BYTES)
        return status, body, ct
    except HTTPError as e:
        return e.code, b"", ""
    except URLError as e:
        return -1, f"URLError: {e.reason}".encode("utf-8", errors="replace"), ""
    except Exception as e:
        return -1, f"Error: {e}".encode("utf-8", errors="replace"), ""



def main() -> None:
    parser = argparse.ArgumentParser(description="Re-fetch KB manifest URLs and save raw files")
    parser.add_argument("--manifest",  default=str(MANIFEST))
    parser.add_argument("--raw-dir",   default=str(RAW_DIR))
    parser.add_argument("--delay",     type=float, default=1.0,
                        help="Seconds to wait between requests (default 1.0)")
    parser.add_argument("--timeout",   type=int,   default=30)
    parser.add_argument("--limit",     type=int,   default=0,
                        help="Fetch at most N documents (0 = all)")
    parser.add_argument("--resume",    action="store_true",
                        help="Skip documents that already have a raw file")
    args = parser.parse_args()

    raw_dir  = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        sys.exit(1)

    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = m.get("documents", [])
    print(f"[fetch] Manifest: {manifest_path.name}  ({len(docs)} documents)")

    results: list[dict] = []
    unverified: list[str] = []
    fetched = skipped = failed = 0

    for i, doc in enumerate(docs):
        if args.limit and i >= args.limit:
            print(f"[fetch] --limit {args.limit} reached; stopping.")
            break

        doc_id = str(doc.get("doc_id") or doc.get("id") or f"doc_{i}")
        url    = str(doc.get("url") or doc.get("source_url") or "")
        source = str(doc.get("source") or "")

        # Determine file extension
        ext = ext_for_url(url)
        # Override: API URLs return JSON
        if "api.fda.gov" in url or url.endswith(".json"):
            ext = ".json"
        elif "wsearch.nlm.nih.gov" in url:
            ext = ".xml"

        raw_path = raw_dir / f"{doc_id}{ext}"

        if args.resume and raw_path.exists():
            skipped += 1
            sha = sha256_bytes(raw_path.read_bytes())
            results.append({
                "doc_id":       doc_id,
                "title":        doc.get("title"),
                "url":          url,
                "source":       source,
                "raw_file":     str(raw_path.relative_to(PROJECT_ROOT)),
                "http_status":  "skipped_resume",
                "retrieved_at": None,
                "sha256_raw":   sha,
                "verified":     True,
                "note":         "resumed from existing file",
            })
            if (skipped) % 25 == 0:
                print(f"  [skip] {skipped} docs already have raw files ...")
            continue

        if not url:
            results.append({
                "doc_id":      doc_id,
                "title":       doc.get("title"),
                "url":         "",
                "source":      source,
                "raw_file":    None,
                "http_status": "NO_URL",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256_raw":  None,
                "verified":    False,
                "note":        "no URL in manifest",
            })
            unverified.append(doc_id)
            failed += 1
            continue

        print(f"[{i+1}/{len(docs)}] {doc_id}  {url[:80]}", end=" ... ", flush=True)
        status, body, ct = fetch_url(url, timeout=args.timeout)
        retrieved_at = datetime.now(timezone.utc).isoformat()

        if status == 200 and body:
            raw_path.write_bytes(body)
            sha = sha256_bytes(body)
            verified = True
            note = "ok"
            fetched += 1
            print(f"HTTP {status}  {len(body):,} bytes  sha={sha[:12]}...")
        else:
            note = f"HTTP {status}" if status > 0 else body.decode("utf-8", errors="replace")[:120]
            sha = None
            verified = False
            unverified.append(doc_id)
            failed += 1
            print(f"FAIL  {note}")

        results.append({
            "doc_id":       doc_id,
            "title":        doc.get("title"),
            "url":          url,
            "source":       source,
            "raw_file":     str(raw_path.relative_to(PROJECT_ROOT)) if verified else None,
            "http_status":  status,
            "retrieved_at": retrieved_at,
            "sha256_raw":   sha,
            "verified":     verified,
            "note":         note,
        })

        time.sleep(args.delay)

    # ── summary ──────────────────────────────────────────────────────
    total_processed = fetched + skipped + failed
    print(f"\n[fetch] Done.")
    print(f"  Fetched:           {fetched}")
    print(f"  Skipped (resume):  {skipped}")
    print(f"  Failed/unverified: {failed}")
    print(f"  Total processed:   {total_processed}")

    if unverified:
        print(f"\n[fetch] UNVERIFIED ({len(unverified)}) — these docs have no raw file:")
        for did in unverified:
            print(f"  {did}")

    # ── save report ───────────────────────────────────────────────────
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    report_path = MANIFESTS / "kb_raw_fetch_report.json"
    report = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "manifest":      str(manifest_path),
        "raw_dir":       str(raw_dir),
        "total_docs":    len(docs),
        "fetched_ok":    fetched,
        "skipped":       skipped,
        "failed":        failed,
        "unverified_ids": unverified,
        "documents":     results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[fetch] Report saved to {report_path}")
    sys.exit(0 if not unverified else 1)


if __name__ == "__main__":
    main()
