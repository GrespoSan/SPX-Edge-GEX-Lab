"""Bounded GET-only access to existing private Supabase snapshot objects.

This module never lists, uploads, signs, changes policies, or administers Supabase.
It cannot prove a token's RLS privileges: the owner must verify those beforehand.
"""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpx

from edge_clone_engine import MAX_UPLOAD_BYTES

BUCKET = "spx-snapshots"


class StorageReadError(ValueError):
    """Safe to show to the user: no URLs, tokens or remote response bodies."""


def _project_url(value):
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname
            or not re.fullmatch(r"[a-z0-9-]+\.supabase\.co", parts.hostname)
            or parts.netloc != parts.hostname or parts.path not in ("", "/")
            or parts.query or parts.fragment):
        raise StorageReadError("SUPABASE_URL deve essere l'URL HTTPS del progetto supabase.co.")
    return "https://" + parts.hostname


def _object_path(value):
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise StorageReadError("Indicare il percorso completo di una fotografia nel bucket.")
    segments = value.split("/")
    if any(part in ("", ".", "..") or unquote(part) in (".", "..")
           or "/" in unquote(part) or "\\" in unquote(part) for part in segments):
        raise StorageReadError("Percorso fotografia non valido.")
    if not value.endswith((".json", ".json.gz")):
        raise StorageReadError("Selezionare una fotografia .json o .json.gz.")
    return "/".join(quote(part, safe="") for part in segments)


def _nonprivileged(value, *, jwt_required=False):
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise StorageReadError("Credenziale di lettura mancante o non valida.")
    if value.startswith("sb_secret_"):
        raise StorageReadError("Le chiavi Supabase privilegiate sono vietate in Edge.")
    if value.startswith("sb_publishable_") and not jwt_required:
        return
    try:
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        role = claims.get("role")
    except (ValueError, TypeError, AttributeError):
        raise StorageReadError("Attesa una chiave publishable/anon o un JWT di lettura.") from None
    # This is only a local exclusion check, not signature or privilege verification.
    if not isinstance(role, str) or role.lower() in ("service_role", "supabase_admin", "postgres"):
        raise StorageReadError("JWT privilegiato o privo di ruolo: accesso rifiutato.")


def _download(url, headers, transport=None):
    try:
        with httpx.Client(timeout=35, follow_redirects=False, transport=transport) as client:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise StorageReadError(
                        f"Lettura Supabase non riuscita (HTTP {response.status_code}). "
                        "Verificare autorizzazione, percorso e scadenza senza modificare le policy.")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise StorageReadError("Fotografia superiore al limite di 25 MiB.")
                    chunks.append(chunk)
                if not size:
                    raise StorageReadError("Fotografia vuota.")
                return b"".join(chunks)
    except httpx.HTTPError:
        raise StorageReadError("Connessione Supabase non disponibile; dettagli e credenziali omessi.") from None


def read_object(project_url, object_path, api_key, read_token, *, read_only_confirmed=False, transport=None):
    if read_only_confirmed is not True:
        raise StorageReadError("Serve la conferma del proprietario sui privilegi già limitati alla lettura.")
    base = _project_url(project_url)
    path = _object_path(object_path)
    _nonprivileged(api_key)
    _nonprivileged(read_token, jwt_required=True)
    return _download(base + "/storage/v1/object/authenticated/" + BUCKET + "/" + path,
                     {"apikey": api_key, "Authorization": "Bearer " + read_token}, transport)


def read_signed_snapshot(signed_url, *, project_url="", transport=None):
    try:
        parts = urlsplit(signed_url)
        base = _project_url("https://" + parts.netloc)
        if project_url and base != _project_url(project_url):
            raise StorageReadError("L'URL firmato non appartiene al progetto configurato.")
        prefix = "/storage/v1/object/sign/" + BUCKET + "/"
        if (parts.scheme != "https" or not parts.path.startswith(prefix) or parts.fragment
                or not parse_qs(parts.query).get("token")):
            raise StorageReadError("Atteso un URL firmato per una fotografia in spx-snapshots.")
        _object_path(unquote(parts.path[len(prefix):]))
    except (ValueError, AttributeError):
        raise StorageReadError("URL firmato Supabase non valido; contenuto omesso.") from None
    return _download(signed_url, {}, transport)
