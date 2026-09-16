"""Conservative joins between captured Likes and explicit post author metadata."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


def post_code(url):
    try:
        parts = urlsplit(url)
        if parts.hostname not in {"instagram.com", "www.instagram.com"}:
            return None
        match = re.fullmatch(r"/(?:p|reel|reels)/([A-Za-z0-9_-]+)/?", parts.path)
        return match.group(1) if match else None
    except ValueError:
        return None


def metadata_endpoint(url):
    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.hostname in {"instagram.com", "www.instagram.com"} and (
            parts.path in {"/api/graphql", "/graphql/query", "/graphql/query/",
                           "/ajax/route-definition/", "/ajax/navigation/", "/ajax/bulk-route-definitions/"}
            or re.fullmatch(r"/api/v1/media/[0-9_]+/info/", parts.path) is not None
        )
    except ValueError:
        return False


def numeric(value):
    if type(value) not in (str, int):
        return None
    text = str(value)
    return text if re.fullmatch(r"[1-9][0-9]*", text) else None


class _JsonScripts(HTMLParser):
    """Read inert JSON scripts from a post document, never execute page code."""
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type", "").lower() in {"application/json", "application/ld+json"}
            self.parts = []

    def handle_data(self, text):
        if self.active:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.parts))
            self.active = False


def documents(body):
    body = body.lstrip().removeprefix("for (;;);").lstrip()
    if body.startswith("<"):
        parser = _JsonScripts()
        parser.feed(body)
        chunks = parser.scripts
    else:
        try:
            return [json.loads(body)]
        except ValueError:
            chunks = body.splitlines()  # Incremental GraphQL JSON records.
    result = []
    for chunk in chunks:
        try:
            result.append(json.loads(chunk))
        except ValueError:
            pass
    return result


def inspect_metadata(body, expected_code=None):
    """Read explicit owner/user IDs from media nodes, never from display text."""
    found = []
    docs = documents(body)
    diagnostic = {"json_documents": len(docs), "media_nodes": 0, "with_author": 0,
                  "with_media_id": 0, "code_matches": 0, "error_nodes": 0}
    stack = list(docs)
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if node.get("errors") or node.get("status") == "fail":
                diagnostic["error_nodes"] += 1
                continue
            # A route result scopes its concrete instanceParams to its view props.
            # routeParams describes parameter types; it does not contain values.
            infos = node.get("route_match_infos")
            exports = node.get("exports")
            if isinstance(infos, list) and isinstance(exports, dict):
                codes = set()
                for info in infos:
                    params = info.get("instanceParams", {}) if isinstance(info, dict) else {}
                    value = params.get("shortcode") if isinstance(params, dict) else None
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value):
                        codes.add(value)
                if len(codes) == 1:
                    route_code = next(iter(codes))
                    for view in ("rootView", "hostableView"):
                        export = exports.get(view, {})
                        props = export.get("props", {}) if isinstance(export, dict) else {}
                        if not isinstance(props, dict):
                            continue
                        pk = numeric(props.get("media_id"))
                        owner = numeric(props.get("media_owner_id"))
                        if pk and owner:
                            # Reuse the ordinary node validation and diagnostics.
                            stack.append({"pk": pk, "code": route_code, "owner": {"id": owner}})
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
                elif isinstance(value, str) and value.startswith(('{', '[')):
                    try:
                        stack.append(json.loads(value))
                    except ValueError:
                        pass
            code = node.get("code") or node.get("shortcode")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
                continue
            diagnostic["media_nodes"] += 1
            media_pk = numeric(str(node.get("pk") or node.get("id") or "").split("_", 1)[0])
            authors = set()
            for field in ("owner", "user"):
                user = node.get(field)
                if isinstance(user, dict):
                    for key in ("pk", "id"):
                        author = numeric(user.get(key))
                        if author:
                            authors.add(author)
            diagnostic["with_author"] += bool(authors)
            diagnostic["with_media_id"] += bool(media_pk)
            if expected_code is not None and code != expected_code:
                continue
            diagnostic["code_matches"] += 1
            if media_pk and authors:
                found.append((media_pk, code, authors))
    return found, diagnostic


def metadata(body, expected_code=None):
    return inspect_metadata(body, expected_code)[0]


class AuthorTracker:
    def __init__(self):
        self.likes = {}
        self.details = {}
        self.reported = {}
        self.products = {}

    def add_likes(self, records):
        for composite, (code, *_rest) in records.items():
            pk, suffix = composite.split("_", 1)
            self.likes.setdefault((pk, code), set()).add(suffix)
            self.products.setdefault((pk, code), set()).add(_rest[0] if _rest else "unknown")
        return self.results()

    def add_details(self, rows):
        for pk, code, authors in rows:
            self.details.setdefault((pk, code), set()).update(authors)
        return self.results()

    def results(self):
        changes = []
        for index, (key, candidates) in enumerate(self.likes.items(), 1):
            authors = self.details.get(key)
            if not authors:
                continue
            if len(authors) != 1 or len(candidates) != 1:
                state = "conflicting"
            else:
                state = "matched" if authors == candidates else "mismatched"
            if self.reported.get(key) != state:
                self.reported[key] = state
                changes.append((index, state))
        return changes

    def preview(self, author_id=None):
        """Return all observations; filtering never treats ambiguous IDs as known."""
        rows = []
        for index, (key, candidates) in enumerate(self.likes.items(), 1):
            authors = self.details.get(key, set())
            state = self.reported.get(key, "inferred")
            if len(candidates) != 1 or len(authors) > 1:
                state = "conflicting"
            identity = authors or candidates
            author = next(iter(identity)) if len(identity) == 1 and state != "conflicting" else None
            if author_id is not None and author != author_id:
                continue
            products = self.products.get(key, {"unknown"})
            product = next(iter(products)) if len(products) == 1 else "unknown"
            rows.append({"index": index, "media_id": key[0], "code": key[1],
                         "product": product, "author_id": author, "evidence": state})
        return rows
