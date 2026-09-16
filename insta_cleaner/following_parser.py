"""Collect account-scoped following pages without making requests."""

import json
import re
from urllib.parse import parse_qs, urlsplit

from .authors import documents, numeric


def following_request(url):
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in {'instagram.com', 'www.instagram.com'}:
            return None
        match = re.fullmatch(r'/api/v1/friendships/([1-9][0-9]*)/following/', parts.path)
        if not match:
            return None
        query = parse_qs(parts.query, keep_blank_values=True)
        # Search and other filters are not complete following-list traversals.
        valid = set(query) <= {'count', 'max_id'} and all(len(v) == 1 for v in query.values())
        return match.group(1), query.get('max_id', [''])[0], valid
    except ValueError:
        return None


class FollowingTracker:
    def __init__(self):
        self.accounts = {}
        self.expected = {}

    def profile_counts(self, body):
        stack = documents(body)
        changed = set()
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if node.get('errors') or node.get('status') == 'fail':
                    continue
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
                account = numeric(node.get('pk') or node.get('id'))
                count = node.get('following_count')
                if account and type(count) is int and count >= 0:
                    if self.expected.get(account) != count:
                        self.expected[account] = count
                        changed.add(account)
        return changed

    def add(self, request, status, body):
        account, cursor, valid = request
        state = self.accounts.setdefault(account, {'pages': {}, 'failed': False, 'reasons': set()})
        reason = 'invalid JSON or response body unavailable'
        try:
            if not valid:
                reason = 'unsupported request parameters (possibly a filtered list)'
                raise ValueError()
            if status != 200:
                reason = f'HTTP {status}' if status else 'response body could not be read'
                raise ValueError()
            data = json.loads(body)
            reason = 'response does not report status ok'
            if data.get('status') != 'ok':
                raise ValueError()
            reason = 'users field missing or not a list'
            users = data['users']
            if not isinstance(users, list):
                raise ValueError()
            records = {}
            reason = 'user record lacks a supported account ID or username'
            for user in users:
                pk = numeric(user.get('pk'))
                username = user.get('username')
                if not pk or not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.]+', username):
                    raise ValueError()
                records[pk] = username
            more = data.get('has_more')
            next_cursor = data.get('next_max_id') or ''
            reason = 'unsupported has_more or next_max_id field type'
            if type(more) is not bool or not isinstance(next_cursor, str):
                raise ValueError()
            if bool(next_cursor) != more:
                reason = 'has_more and next_max_id disagree'
                raise ValueError()
            unrestricted = (data.get('should_limit_list_of_followings') is False
                            and type(data.get('hidden_following_account_count')) is int
                            and data['hidden_following_account_count'] == 0)
            page = (records, next_cursor, more, unrestricted)
            old = state['pages'].get(cursor)
            # A renamed account is still the same member. Compare membership and
            # pagination separately from display names.
            if old is not None and (set(old[0]) != set(records) or old[1:] != page[1:]):
                state['failed'] = True  # Snapshot changed; restart observation.
                state['reasons'].add('repeated cursor returned different members, pagination, or restrictions')
            state['pages'][cursor] = page
        except (ValueError, KeyError, TypeError, AttributeError):
            state['failed'] = True
            state['reasons'].add(reason)
        return self.summary(account)

    def summary(self, account):
        state = self.accounts[account]
        pages = state['pages']
        users = {}
        for records, *_ in pages.values():
            users.update(records)
        cursor, seen, terminal, restricted = '', set(), False, False
        while cursor in pages and cursor not in seen:
            seen.add(cursor)
            _, next_cursor, more, unrestricted = pages[cursor]
            restricted |= not unrestricted
            if not more:
                terminal = True
                break
            cursor = next_cursor
        expected = self.expected.get(account)
        complete = (terminal and not restricted and not state['failed'] and len(seen) == len(pages)
                    and (expected is None or expected == len(users)))
        return {'users': len(users), 'pages': len(pages), 'expected': expected,
                'complete': complete, 'terminal': terminal, 'failed': state['failed'],
                'reasons': sorted(state['reasons'])}

    def show(self, account):
        if account not in self.accounts:
            return
        result = self.summary(account)
        label = list(self.accounts).index(account) + 1
        expected = str(result['expected']) if result['expected'] is not None else 'unknown'
        state = 'complete observed traversal' if result['complete'] else 'INCOMPLETE'
        print(f"Following list #{label}: {result['users']} unique accounts; profile count {expected}; "
              f"{result['pages']} pages; {state}.", flush=True)
        if result['failed']:
            print('  Following diagnostic: ' + '; '.join(result['reasons']) + '.')
            print('  Collection continues, but this run cannot establish completeness.')
        elif not result['terminal']:
            print('  More pages are needed to reach the end of the list.')
        print('  List owner is not yet verified as the signed-in account; no negative membership filter is enabled.')
