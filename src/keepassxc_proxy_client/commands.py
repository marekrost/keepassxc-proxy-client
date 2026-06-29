"""CLI command handlers.

Each `cmd_*` function takes a parsed argparse Namespace and either prints a
result to stdout or raises a typed `ProxyClientError` subclass from
`keepassxc_proxy_client.errors`. `__main__.main()` catches these, prints a
one-line message to stderr, and exits with the documented exit code.
"""
import sys
import json
import base64
import socket as _socket

import keepassxc_proxy_client.protocol
from keepassxc_proxy_client import keystore
from keepassxc_proxy_client.errors import (
    AssociationFailed,
    ProxyClientError,
    DatabaseLocked,
    EntryNotFound,
    FieldMissing,
    ProtocolError,
    SocketUnavailable,
)

_FLATPAK_HINT = (
    "permission denied reaching KeePassXC's Browser Integration socket — "
    "typically means KeePassXC is running as a Flatpak and its socket lives "
    "inside the sandbox. Install the native KeePassXC package instead, or "
    "run this tool via flatpak-spawn."
)


def _open_connection(socket_path=None):
    """Construct a Connection and call connect(), mapping socket errors to typed exceptions."""
    connection = keepassxc_proxy_client.protocol.Connection()
    try:
        connection.connect(path=socket_path) if socket_path else connection.connect()
    except PermissionError:
        raise SocketUnavailable(_FLATPAK_HINT)
    except (FileNotFoundError, ConnectionRefusedError, _socket.error) as e:
        raise SocketUnavailable(
            "could not reach KeePassXC's Browser Integration socket: %s "
            "(is KeePassXC running with browser integration enabled?)" % e
        )
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        raise ProtocolError("handshake failed: %s" % (e.args[0] if e.args else e))
    return connection


def _error_code(exc):
    """Pull the numeric errorCode out of a ResponseUnsuccesfulException payload."""
    if not exc.args:
        return None
    payload = exc.args[0]
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode")
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _load_for_use(path, assoc_id):
    """Return a list of (assoc_id, key_bytes) candidates to try.

    Raises ProxyClientError-derived exceptions for missing/empty stores.
    """
    try:
        if assoc_id:
            return [(assoc_id, keystore.load(path, assoc_id))]

        ids = keystore.list_associations(path)
        if not ids:
            raise AssociationFailed("no associations stored in %s" % path)
        return [(aid, keystore.load(path, aid)) for aid in ids]
    except keystore.AssociationNotFound as e:
        raise AssociationFailed(str(e))
    except (FileNotFoundError, keystore.KeystoreError) as e:
        raise AssociationFailed("keystore error: %s" % e)


def _connect_and_authenticate(socket_path, file, assoc_id):
    """Open a connection, try each candidate association, return the first that works.

    Raises:
      SocketUnavailable — connect() failed.
      AssociationFailed — keystore problems, or no candidate authenticated for non-lock reasons.
      DatabaseLocked — every candidate's test-associate reported errorCode 1.
      ProtocolError — handshake or other unclassified protocol failure.
    """
    candidates = _load_for_use(file, assoc_id)
    connection = _open_connection(socket_path)

    saw_locked = False
    last_other = None
    for aid, key_bytes in candidates:
        connection.load_associate(aid, key_bytes)
        try:
            if connection.test_associate():
                return connection
        except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
            if _error_code(e) == 1:
                saw_locked = True
            else:
                last_other = e
            continue

    # No candidate authenticated. Prefer the more specific signal.
    if saw_locked and last_other is None:
        raise DatabaseLocked(
            "no KeePassXC database is unlocked under the stored association(s)"
        )
    if assoc_id:
        raise AssociationFailed(
            "association id %r is not valid for the running KeePassXC instance" % assoc_id
        )
    raise AssociationFailed(
        "none of the stored associations are valid for the running KeePassXC instance"
    )


_DIRECT_FIELDS = {
    "password": "password",
    "login": "login",
    "username": "login",
    "name": "name",
    "title": "name",
    "uuid": "uuid",
}


def _extract_field(entry, field):
    """Return the requested field from a get-logins entry.

    Returns None if the field is not present on the entry. Raises ValueError
    if the field name is unrecognised (caller maps that to FieldMissing).
    """
    key = field.lower()
    if key in _DIRECT_FIELDS:
        return entry.get(_DIRECT_FIELDS[key])

    if key.startswith("attr:"):
        attr_name = field.split(":", 1)[1]
        for sf in entry.get("stringFields", []) or []:
            value = sf.get("KPH: " + attr_name)
            if value is not None:
                return value
        return None

    raise ValueError("unknown field %r" % field)


def _emit_field(matches, field, all_flag, match_description):
    """Print `field` for one or all of `matches`.

    Raises EntryNotFound / FieldMissing on the documented failure modes.
    """
    if not matches:
        raise EntryNotFound("no entries found for the given %s" % match_description)

    entries = matches if all_flag else matches[:1]

    if not all_flag and len(matches) > 1:
        print(
            "warning: %d entries match this %s; printing the first. "
            "Pass --all to print every match." % (len(matches), match_description),
            file=sys.stderr,
        )

    try:
        values = [_extract_field(e, field) for e in entries]
    except ValueError as e:
        raise FieldMissing(str(e))

    missing = [i for i, v in enumerate(values) if v is None]
    if missing:
        if len(entries) == 1:
            raise FieldMissing("field %r is not present on the matching entry" % field)
        raise FieldMissing(
            "field %r is not present on %d of %d matching entries"
            % (field, len(missing), len(entries))
        )

    for v in values:
        print(v)


def _normalize_path(path):
    """Normalize a user-supplied entry path to `comp1/comp2/.../title`.

    Leading slash is optional. Empty components are dropped.
    """
    return "/".join(c for c in path.split("/") if c)


def _entry_full_path(entry):
    """Return the slash-joined `group/title` for a get-database-entries entry."""
    group = entry.get("group", "") or ""
    title = entry.get("title", "") or ""
    if group:
        return group.rstrip("/") + "/" + title
    return title


def cmd_create(args):
    connection = _open_connection(args.socket)
    try:
        connection.associate()
        if not connection.test_associate():
            raise ProtocolError(
                "newly created association reports as invalid (unexpected)"
            )
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        raise ProtocolError("associate failed: %s" % (e.args[0] if e.args else e))

    assoc_id, public_key = connection.dump_associate()

    if args.save:
        try:
            keystore.save(args.file, assoc_id, public_key, force=args.force)
        except keystore.AssociationExists as e:
            raise AssociationFailed(str(e))
        print("saved association id %r to %s" % (assoc_id, args.file))
        return

    out = {
        "id": assoc_id,
        "public_key": base64.b64encode(public_key).decode("utf-8"),
    }
    print(json.dumps(out))


def cmd_get(args):
    connection = _connect_and_authenticate(args.socket, args.file, args.id)
    try:
        logins = connection.get_logins(args.url) or []
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        # Per §4: after a successful test-associate, errorCode 1 from
        # get-logins means "no matching entry," not "database locked."
        if _error_code(e) == 1:
            logins = []
        else:
            raise ProtocolError("get-logins failed: %s" % (e.args[0] if e.args else e))
    _emit_field(logins, args.field, args.all, "URL")


def cmd_get_by_path(args):
    connection = _connect_and_authenticate(args.socket, args.file, args.id)

    try:
        response = connection.get_database_entries()
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        raise ProtocolError(
            "get-database-entries failed: %s "
            "(this action requires \"Allow access to entries\" in KeePassXC's "
            "Browser Integration settings for the chosen association)"
            % (e.args[0] if e.args else e)
        )

    target = _normalize_path(args.path)
    matches = [
        e for e in (response.get("entries") or [])
        if _normalize_path(_entry_full_path(e)) == target
    ]
    _emit_field(matches, args.field, args.all, "path")


def cmd_totp(args):
    connection = _connect_and_authenticate(args.socket, args.file, args.id)

    try:
        totp = connection.get_totp(args.uuid)
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        raise ProtocolError("get-totp failed: %s" % (e.args[0] if e.args else e))

    if not totp:
        raise EntryNotFound("no TOTP found for the given UUID")

    print(totp)


def cmd_unlock(args):
    candidates = _load_for_use(args.file, args.id)
    connection = _open_connection(args.socket)
    # For unlock we only use the first candidate, since the user-visible effect
    # (the unlock dialog) does not depend on which association we authenticate as.
    assoc_id, key_bytes = candidates[0]
    connection.load_associate(assoc_id, key_bytes)

    try:
        print(connection.test_associate(True))
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        # On unlock, errorCode 1 (database not opened) is the expected state;
        # we triggered the dialog and returning that signal is fine.
        if _error_code(e) == 1:
            print("False")
        else:
            raise ProtocolError("unlock failed: %s" % (e.args[0] if e.args else e))


def cmd_list(args):
    try:
        ids = keystore.list_associations(args.file)
    except (FileNotFoundError, keystore.KeystoreError) as e:
        raise ProxyClientError("keystore error: %s" % e)

    for aid in ids:
        print(aid)
