"""Private, automatic reading of the existing SPX archive.

Auth sessions are renewed in memory. Storage calls only list/download existing
objects; this module creates no users, policies, objects or archive jobs.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
import json
import re
import time
from uuid import UUID

import httpx

from edge_storage import StorageReadError, _download, _nonprivileged, _project_url

RAW_NAME = re.compile(r'^SPX_CBOE_(\d{8})_(\d{6})\.json(?:\.gz)?$')
WEEK_NAME = re.compile(r'^(\d{4})-W(\d{2})$')
PAGE_SIZE = 1000
MAX_PAGES = 20


@dataclass(repr=False)
class ReaderSession:
    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str


@dataclass(frozen=True)
class SnapshotRef:
    path: str
    updated_at: str


def reader_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise StorageReadError('Identificativo utenza Edge non configurato correttamente.') from None


def _claims(token):
    try:
        part = token.split('.')[1]
        obj = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        if not isinstance(obj, dict):
            raise ValueError
        return obj
    except (ValueError, IndexError, TypeError, AttributeError):
        raise StorageReadError('Risposta di autenticazione non valida; dettagli omessi.') from None


def _public_key(key):
    _nonprivileged(key)
    if not key.startswith('sb_publishable_') and _claims(key).get('role') != 'anon':
        raise StorageReadError('Usare soltanto la chiave publishable/anon del progetto.')


def _post(base, endpoint, key, body, *, token='', transport=None):
    _public_key(key)
    headers = {'apikey': key}
    if token:
        _nonprivileged(token, jwt_required=True)
        headers['Authorization'] = 'Bearer ' + token
    try:
        with httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client:
            with client.stream('POST', base + endpoint, headers=headers, json=body) as response:
                if response.status_code != 200:
                    raise StorageReadError(f'Richiesta di lettura/accesso non riuscita (HTTP {response.status_code}).')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise StorageReadError('Risposta troppo grande; lettura interrotta.')
                    chunks.append(chunk)
                return json.loads(b''.join(chunks))
    except StorageReadError:
        raise
    except httpx.HTTPError:
        raise StorageReadError('Connessione all’archivio non disponibile; dettagli e credenziali omessi.') from None
    except (ValueError, UnicodeError):
        raise StorageReadError('Risposta dell’archivio non valida; dettagli omessi.') from None


def _session(response, expected_id, now):
    try:
        token, refresh = response['access_token'], response['refresh_token']
        _nonprivileged(token, jwt_required=True)
        claims = _claims(token)
        expiry = float(claims['exp'])
        if (claims.get('role') != 'authenticated' or claims.get('sub') != expected_id
                or response['user']['id'] != expected_id or response['user'].get('is_anonymous')
                or not isinstance(refresh, str) or not refresh or not now + 30 < expiry < now + 86400 * 7):
            raise ValueError
    except (KeyError, ValueError, TypeError, OverflowError):
        raise StorageReadError('Accesso consentito esclusivamente all’utenza Edge configurata.') from None
    return ReaderSession(token, refresh, expiry, expected_id)


def login_reader(project_url, api_key, email, password, expected_user_id, *, transport=None, now=None):
    expected = reader_id(expected_user_id)
    base = _project_url(project_url)
    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        raise StorageReadError('Inserire email e password dell’utenza Edge dedicata.')
    response = _post(base, '/auth/v1/token?grant_type=password', api_key,
                     {'email': email.strip(), 'password': password}, transport=transport)
    return _session(response, expected, time.time() if now is None else now)


def renew_reader(project_url, api_key, session, expected_user_id, *, transport=None, now=None):
    expected = reader_id(expected_user_id)
    current = time.time() if now is None else now
    if not isinstance(session, ReaderSession) or session.user_id != expected:
        raise StorageReadError('Sessione Edge non valida: accedere nuovamente.')
    if session.expires_at > current + 60:
        return session
    response = _post(_project_url(project_url), '/auth/v1/token?grant_type=refresh_token', api_key,
                     {'refresh_token': session.refresh_token}, transport=transport)
    return _session(response, expected, current)


def _entries(base, key, token, prefix, transport):
    for page in range(MAX_PAGES):
        rows = _post(base, '/storage/v1/object/list/spx-snapshots', key,
                     {'prefix': prefix, 'limit': PAGE_SIZE, 'offset': page * PAGE_SIZE,
                      'sortBy': {'column': 'name', 'order': 'desc'}}, token=token, transport=transport)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise StorageReadError('Elenco dell’archivio non valido.')
        yield rows
        if len(rows) < PAGE_SIZE:
            return
    raise StorageReadError('Archivio oltre il limite di paginazione: nessuna fotografia selezionata.')


def latest_snapshot(project_url, api_key, session, *, transport=None, now=None):
    current = time.time() if now is None else now
    if not isinstance(session, ReaderSession) or session.expires_at <= current + 15:
        raise StorageReadError('Sessione scaduta: accedere nuovamente.')
    base = _project_url(project_url)
    weeks = set()
    for rows in _entries(base, api_key, session.access_token, '', transport):
        for row in rows:
            match = WEEK_NAME.fullmatch(str(row.get('name', '')))
            if match:
                try:
                    date.fromisocalendar(int(match[1]), int(match[2]), 1)
                    weeks.add(match[0])
                except ValueError:
                    continue
    # Select the newest CBOE source timestamp among *all* listing pages.
    # The filename timestamp is not proof of the actual download time.
    for week in sorted(weeks, reverse=True):
        prefix = week + '/snapshots'
        candidates = []
        for rows in _entries(base, api_key, session.access_token, prefix, transport):
            for row in rows:
                name = row.get('name', '')
                match = RAW_NAME.fullmatch(name) if isinstance(name, str) else None
                if match:
                    try:
                        stamp = datetime.strptime(match[1] + match[2], '%Y%m%d%H%M%S')
                    except ValueError:
                        continue
                    candidates.append((stamp, name, str(row.get('updated_at') or '')))
        if candidates:
            _, name, updated = max(candidates)
            return SnapshotRef(prefix + '/' + name, updated)
    raise StorageReadError('Nessuna fotografia SPX grezza disponibile nelle settimane archiviate.')


def download_snapshot(project_url, api_key, session, snapshot, *, transport=None, now=None):
    current = time.time() if now is None else now
    if not isinstance(session, ReaderSession) or session.expires_at <= current + 15:
        raise StorageReadError('Sessione scaduta: accedere nuovamente.')
    if not isinstance(snapshot, SnapshotRef) or not re.fullmatch(
            r'\d{4}-W\d{2}/snapshots/SPX_CBOE_\d{8}_\d{6}\.json(?:\.gz)?', snapshot.path):
        raise StorageReadError('Percorso non appartenente alle fotografie SPX grezze.')
    _public_key(api_key)
    _nonprivileged(session.access_token, jwt_required=True)
    return _download(_project_url(project_url) + '/storage/v1/object/authenticated/spx-snapshots/' + snapshot.path,
                     {'apikey': api_key, 'Authorization': 'Bearer ' + session.access_token}, transport)

def snapshots_for_day(project_url, api_key, session, selected_day, *, transport=None, now=None):
    """List existing original SPX snapshots for an archive date; no writes."""
    current = time.time() if now is None else now
    if not isinstance(session, ReaderSession) or session.expires_at <= current + 15:
        raise StorageReadError('Sessione scaduta: accedere nuovamente.')
    if not isinstance(selected_day, date):
        raise StorageReadError('Data archivio non valida.')
    year, week, _ = selected_day.isocalendar()
    prefix = f'{year}-W{week:02d}/snapshots'
    expected = selected_day.strftime('%Y%m%d')
    found = []
    for rows in _entries(_project_url(project_url), api_key, session.access_token, prefix, transport):
        for row in rows:
            name = row.get('name', '')
            if not isinstance(name, str):
                continue
            match = RAW_NAME.fullmatch(name)
            if not match or match[1] != expected:
                continue
            try:
                datetime.strptime(match[1] + match[2], '%Y%m%d%H%M%S')
            except ValueError:
                continue
            found.append(SnapshotRef(prefix + '/' + name, str(row.get('updated_at') or '')))
    return sorted(found, key=lambda item: item.path)


def snapshot_acquisition_status(project_url, api_key, session, snapshot, *, transport=None, now=None):
    """Return (verified Rome download time, reason) using read-only Serafini logs."""
    from zoneinfo import ZoneInfo
    if not isinstance(snapshot, SnapshotRef):
        return None, 'Riferimento fotografia non valido.'
    current = time.time() if now is None else now
    if not isinstance(session, ReaderSession) or session.expires_at <= current + 15:
        return None, 'Sessione Edge scaduta.'
    prefix = snapshot.path.split('/snapshots/')[0] + '/logs'
    match, listed, readable, errors = [], 0, 0, 0
    try:
        for rows in _entries(_project_url(project_url), api_key, session.access_token, prefix, transport):
            for entry in rows:
                name = str(entry.get('name', ''))
                if not name.endswith('.json') or '/' in name or '..' in name:
                    continue
                listed += 1
                url = _project_url(project_url) + '/storage/v1/object/authenticated/spx-snapshots/' + prefix + '/' + name
                try:
                    record = json.loads(_download(url, {'apikey': api_key, 'Authorization': 'Bearer ' + session.access_token}, transport))
                    readable += 1
                    if record.get('file') != snapshot.path or record.get('status') not in ('NUOVO', 'INVARIATO'):
                        continue
                    raw = record.get('download_rome') or record.get('download_utc')
                    if not raw:
                        continue
                    stamp = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
                    if stamp.tzinfo is not None:
                        match.append(stamp.astimezone(ZoneInfo('Europe/Rome')))
                except (ValueError, TypeError, KeyError, StorageReadError):
                    errors += 1
    except (StorageReadError, ValueError, TypeError):
        return None, 'Elenco registri non accessibile all’utenza Edge (verificare permessi di sola lettura).'
    if match:
        return min(match), None
    if listed == 0:
        return None, 'Nessun registro visibile all’utenza Edge nella settimana selezionata.'
    if readable == 0:
        return None, 'Registri elencati ma non scaricabili dall’utenza Edge (verificare permessi di lettura).'
    if errors:
        return None, f'Nessuna corrispondenza valida per il file: {readable} registri letti, {errors} non leggibili.'
    return None, f'Nessun registro associato a questa fotografia tra i {readable} registri leggibili.'


def snapshot_acquisition(project_url, api_key, session, snapshot, *, transport=None, now=None):
    """Backward-compatible verified download timestamp, or None."""
    return snapshot_acquisition_status(
        project_url, api_key, session, snapshot, transport=transport, now=now
    )[0]
