"""Read ONLY the existing feed's ES-SPX metadata, never its trading profiles.

The existing publisher and MT4 connection remain unchanged. This module performs
one authenticated GET and does not call Yahoo or any Serafini calculation.
"""
import csv
from datetime import date, datetime, timezone
import io
import re
import time
from zoneinfo import ZoneInfo

import httpx

from edge_archive import ReaderSession, _public_key
from edge_futures import BasisUnavailable, parse_basis
from edge_storage import _nonprivileged, _project_url, StorageReadError

OBJECT_PATH = 'mt4/latest.csv'
HEADER_LIMIT = 8192
TABLE_HEADER = re.compile(rb'(?:^|\r?\n)profile,expiry,strike_spx,price_es,net_gamma\r?\n')
FIELDS = {'schema', 'date_rome', 'basis_es_spx', 'basis_date', 'basis_source', 'published_utc'}


def parse_shared_basis(raw: bytes, target: date, *, now=None) -> dict:
    """Accept the published date and metadata; ignore all profile rows."""
    try:
        match = TABLE_HEADER.search(raw[:HEADER_LIMIT])
        if match is None:
            raise ValueError
        meta = {}
        for row in csv.reader(io.StringIO(raw[:match.start()].decode('utf-8-sig')), strict=True):
            if len(row) != 2 or row[0] in meta:
                raise ValueError
            meta[row[0]] = row[1]
        if not FIELDS <= meta.keys() or meta['schema'] != 'serafini_mt4_v3':
            raise ValueError
        feed_day = date.fromisoformat(meta['date_rome'])
        reference = date.fromisoformat(meta['basis_date'])
        published = datetime.fromisoformat(meta['published_utc'].replace('Z', '+00:00'))
        if (reference >= feed_day or published.tzinfo is None
                or published.timestamp() > (time.time() if now is None else now) + 300
                or published.astimezone(ZoneInfo('Europe/Rome')).date() != feed_day):
            raise ValueError
        basis = parse_basis(meta['basis_es_spx'])
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error, OverflowError):
        raise BasisUnavailable('Metadati del differenziale condiviso non validi; nessun valore applicato.') from None
    if feed_day != target:
        raise BasisUnavailable('Il differenziale condiviso riguarda il ' + feed_day.isoformat()
                               + ', ma la fotografia è del ' + target.isoformat() + '. Nessun valore di un altro giorno viene applicato.')
    return {'basis': basis, 'target_date': feed_day.isoformat(),
            'reference_date': reference.isoformat(), 'published_utc': published.astimezone(timezone.utc).isoformat(),
            'source': 'Archivio APP SPX · ' + OBJECT_PATH,
            'provider_source': meta['basis_source'], 'shared_object': OBJECT_PATH}


def read_shared_basis(project_url, api_key, session, target: date, *, transport=None, now=None) -> dict:
    current = time.time() if now is None else now
    try:
        if not isinstance(session, ReaderSession) or session.expires_at <= current + 15:
            raise BasisUnavailable('Sessione scaduta: accedere nuovamente a Edge.')
        _public_key(api_key)
        _nonprivileged(session.access_token, jwt_required=True)
        url = _project_url(project_url) + '/storage/v1/object/authenticated/spx-snapshots/' + OBJECT_PATH
        headers = {'apikey': api_key, 'Authorization': 'Bearer ' + session.access_token,
                   'Range': 'bytes=0-' + str(HEADER_LIMIT - 1), 'Cache-Control': 'no-cache'}
        with httpx.Client(timeout=12, follow_redirects=False, transport=transport) as client:
            with client.stream('GET', url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    raise BasisUnavailable('Differenziale condiviso non leggibile (HTTP '
                                           + str(response.status_code)
                                           + '). Verificare il permesso SELECT Edge su mt4/latest.csv e la presenza del file.')
                prefix = bytearray()
                for chunk in response.iter_bytes():
                    prefix.extend(chunk[:HEADER_LIMIT - len(prefix)])
                    match = TABLE_HEADER.search(prefix)
                    if match:
                        # Retain only the metadata and table header, never profiles.
                        return parse_shared_basis(bytes(prefix[:match.end()]), target, now=current)
                    if len(prefix) >= HEADER_LIMIT:
                        break
        raise BasisUnavailable('Intestazione del differenziale condiviso assente o troppo grande.')
    except httpx.HTTPError:
        raise BasisUnavailable('Lettura del differenziale condiviso temporaneamente non disponibile; nessun ricalcolo avviato.') from None
    except StorageReadError:
        raise BasisUnavailable('Credenziali di sola lettura Edge non valide; dettagli omessi.') from None
