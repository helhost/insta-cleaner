"""Compose read-only collection and selection; never perform removal actions."""
from datetime import datetime, timezone
import json
from pathlib import Path

from .following import collect_following, session_identity, LoginRequired
from .likes import collect_likes, check_authors


def content_matches(item, content):
    if content == 'all':
        return True
    if content == 'reels':
        return item.get('product') == 'clips'
    if content == 'posts':
        return item.get('product') in {'feed', 'carousel_container'}
    raise ValueError('Unknown content filter')


def select_items(items, *, account_id, following=None, content='all', relationship='all'):
    if content not in {'all', 'reels', 'posts'} or relationship not in {'all', 'followed', 'not-followed', 'unknown'}:
        raise ValueError('Unsupported preview filter')
    selected, unknown = [], []
    for item in items:
        if not content_matches(item, content):
            continue
        explicit = item.get('evidence') in {'matched', 'mismatched'} and bool(item.get('author_id'))
        membership = 'unknown'
        if explicit and following is not None:
            membership = following.membership(item['author_id'], account_id=account_id)
        row = {**item, 'relationship': membership if following else 'not-checked',
               'url': f"https://www.instagram.com/p/{item['code']}/"}
        if following and explicit and following.list_owner_id == account_id:
            row['author_username'] = following.accounts.get(item['author_id'])
        if not explicit or (following is not None and membership == 'unknown'):
            unknown.append(row)
        if relationship == 'all' or (following is not None and membership == relationship):
            selected.append(row)
    return selected, unknown


async def build_preview(context, *, pages=3, content='all', relationship='all'):
    if content not in {'all', 'reels', 'posts'} or relationship not in {'all', 'followed', 'not-followed', 'unknown'}:
        raise ValueError('Unsupported preview filter')
    account, _ = await session_identity(context)
    tracker, collection = await collect_likes(context, pages=pages)
    if collection['account_id'] != account:
        raise LoginRequired('Session changed during collection; discard this preview and rerun.')
    candidates = [item for item in tracker.preview() if content_matches(item, content)]
    if candidates:
        print(f'Checking authors for {len(candidates)} collected {content} items…', flush=True)
        await check_authors(context, tracker, len(candidates), items=candidates)
    following = None
    if relationship != 'all':
        print('Collecting Following for the relationship filter…', flush=True)
        following = await collect_following(context)
        if following.list_owner_id != account:
            raise LoginRequired('Session changed during collection; discard this preview and rerun.')
    if (await session_identity(context))[0] != account:
        raise LoginRequired('Session changed during collection; discard this preview and rerun.')
    selected, unknown = select_items(tracker.preview(), account_id=account, following=following,
                                     content=content, relationship=relationship)
    return {'schema_version': 1, 'read_only': True, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'account_id': account, 'identity_source': 'session_cookie', 'likes_collection': collection,
            'collected_count': len(tracker.likes), 'candidate_count': len(candidates),
            'filters': {'content': content, 'relationship': relationship},
            'following': None if following is None else {'complete': following.complete,
                'count': len(following.accounts), 'stop_reason': following.stop_reason},
            'selected': selected, 'unknown': unknown}


def save_preview(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / ('likes-preview-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x', encoding='utf-8') as file:
        path.chmod(0o600)
        json.dump(report, file, indent=2)
        file.write('\n')
    return path
