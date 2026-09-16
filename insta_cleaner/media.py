"""Parse observed Likes media tuples without executing UI expressions."""
import base64
import json
import re

PREFIX = "com.instagram.privacy.activity_center."
ACTIONS = {"liked_media_screen", "liked_next", "liked_refresh", "liked_unlike"}
# Deliberately narrow: match only the media tuple observed in the capture.
# Do not execute the surrounding server-provided Bloks expressions.
MEDIA = re.compile(
    r'\(bk\.action\.array\.Make,\s*"(\d+_\d+)",\s*'
    r'"([A-Za-z0-9_-]+)",\s*"([a-z_]+)",\s*'
    r'\(bk\.action\.i32\.Const,\s*(\d+)\)'
)


def strings(value):
    """Walk decoded JSON values, never evaluating embedded expressions."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def response_records(entry):
    content = entry.get("response", {}).get("content", {})
    body = content.get("text")
    if not body:
        return {}, "response body missing"
    if content.get("encoding") == "base64":
        body = base64.b64decode(body, validate=True).decode("utf-8")
    body = body.strip()
    if body.startswith("for (;;);"):
        body = body[len("for (;;);"):]
    document = json.loads(body)
    payload = document["payload"]["layout"]["bloks_payload"]
    records = {}
    for expression in strings(payload):
        for media_id, code, product, media_type in MEDIA.findall(expression):
            records[media_id] = (code, product, media_type)
    return records, None if records else "no supported media records found"

