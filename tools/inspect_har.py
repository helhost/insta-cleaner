#!/usr/bin/env python3
"""Inspect captured Instagram Likes activity offline using only the stdlib."""

import argparse
import base64
import binascii
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit


from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from insta_cleaner.media import PREFIX, ACTIONS, MEDIA, strings, response_records


def inspect(entries, summary_only=False):
    all_records = {}
    matched = 0
    warnings = 0
    print("Captured Likes requests (HAR entry numbers start at 1):")
    for number, entry in enumerate(entries, 1):
        request = entry.get("request", {})
        try:
            url = urlsplit(request.get("url", ""))
        except ValueError:
            continue
        host = url.hostname or ""
        if not (host == "instagram.com" or host.endswith(".instagram.com")):
            continue
        if url.path != "/async/wbloks/fetch/":
            continue
        app = dict(parse_qsl(url.query)).get("appid", "")
        if not app.startswith(PREFIX) or app[len(PREFIX):] not in ACTIONS:
            continue
        action = app[len(PREFIX):]
        matched += 1
        try:
            records, warning = response_records(entry)
        except (ValueError, KeyError, TypeError, AttributeError, binascii.Error):
            records, warning = {}, "response format could not be parsed"
        all_records.update(records)
        status = entry.get("response", {}).get("status")
        status = str(status) if type(status) is int else "unknown"
        print(f"  {number:>3}: {action:<20} HTTP {status}, {len(records)} items")
        if warning:
            warnings += 1
            print(f"       Note: {warning}")

    print(f"\n{matched} matching requests; {len(all_records)} unique captured items.")
    counts = Counter(record[1] for record in all_records.values())
    for product, count in sorted(counts.items()):
        print(f"  {product}: {count}")
    if not summary_only and all_records:
        print("\nMEDIA ID                                 POST CODE      PRODUCT              TYPE")
        for media_id, (code, product, media_type) in all_records.items():
            print(f"{media_id:<40} {code:<14} {product:<20} {media_type}")
    print("\nCaptured inventory only; not a current or complete account history.")
    if not matched:
        print("No supported Likes requests found. Check what was recorded.")
    return 1 if warnings or not matched else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Local .har file to inspect")
    parser.add_argument("--summary-only", action="store_true", help="Omit item identifiers")
    args = parser.parse_args()
    try:
        document = json.loads(args.capture.read_text(encoding="utf-8-sig"))
        entries = document["log"]["entries"]
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError("Invalid HAR entries")
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not read a valid HAR file. Check the path and export format.", file=sys.stderr)
        return 2
    return inspect(entries, args.summary_only)


if __name__ == "__main__":
    sys.exit(main())
