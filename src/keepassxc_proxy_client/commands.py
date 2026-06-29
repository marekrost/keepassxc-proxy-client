"""CLI command handlers.

Each `cmd_*` function takes a parsed argparse Namespace and produces side
effects (stdout/stderr writes, optional sys.exit). They are wired to
subcommands in __main__.build_parser via `set_defaults(func=...)`.
"""
import sys
import json
import base64

import keepassxc_proxy_client.protocol
from keepassxc_proxy_client import keystore


def _load_for_use(path, assoc_id):
    """Return a list of (assoc_id, key_bytes) candidates to try.

    If `assoc_id` is given, return just that one (raises AssociationNotFound if missing).
    Otherwise return all associations in the file. If the file holds none, raises.
    """
    if assoc_id:
        return [(assoc_id, keystore.load(path, assoc_id))]

    ids = keystore.list_associations(path)
    if not ids:
        raise keystore.AssociationNotFound(
            "no associations stored in %s" % path
        )
    return [(aid, keystore.load(path, aid)) for aid in ids]


def _connect_and_authenticate(path, assoc_id):
    """Open a connection, try each candidate association, return the first that works.

    Returns the connected Connection. Exits non-zero with a stderr message on failure.
    """
    try:
        candidates = _load_for_use(path, assoc_id)
    except (FileNotFoundError, keystore.KeystoreError) as e:
        print("keystore error: %s" % e, file=sys.stderr)
        sys.exit(1)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()

    last_error = None
    for aid, key_bytes in candidates:
        connection.load_associate(aid, key_bytes)
        try:
            if connection.test_associate():
                return connection
        except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
            last_error = e
            continue

    if assoc_id:
        print("association id %r is not valid for the running KeePassXC instance" % assoc_id, file=sys.stderr)
    else:
        print(
            "none of the stored associations are valid for the running KeePassXC instance",
            file=sys.stderr,
        )
    if last_error is not None:
        print("last protocol error: %s" % last_error, file=sys.stderr)
    sys.exit(1)


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

    `field` is the user-supplied --field value (case-insensitive). Supports the
    direct fields in _DIRECT_FIELDS and `attr:<KEY>` for KeePassXC custom
    string attributes (which are stored as `KPH: <KEY>` in `stringFields`).
    Returns None if the field is not present on the entry.
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
    """Print `field` for one or all of `matches`, with consistent UX.

    `match_description` is a short noun phrase like "URL" or "path" used in
    user-facing messages. Exits non-zero on field errors.
    """
    if not matches:
        print("No entries found for the given %s" % match_description, file=sys.stderr)
        sys.exit(1)

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
        print("error: %s" % e, file=sys.stderr)
        sys.exit(1)

    missing = [i for i, v in enumerate(values) if v is None]
    if missing:
        if len(entries) == 1:
            print(
                "field %r is not present on the matching entry" % field,
                file=sys.stderr,
            )
        else:
            print(
                "field %r is not present on %d of %d matching entries"
                % (field, len(missing), len(entries)),
                file=sys.stderr,
            )
        sys.exit(1)

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
    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.associate()

    if not connection.test_associate():
        print("For some reason the newly created association is invalid, this should not be happening", file=sys.stderr)
        sys.exit(1)

    assoc_id, public_key = connection.dump_associate()

    if args.save:
        path = args.file
        try:
            keystore.save(path, assoc_id, public_key, force=args.force)
        except keystore.AssociationExists as e:
            print("keystore error: %s" % e, file=sys.stderr)
            sys.exit(1)
        print("saved association id %r to %s" % (assoc_id, path))
        return

    out = {
        "id": assoc_id,
        "public_key": base64.b64encode(public_key).decode("utf-8"),
    }
    print(json.dumps(out))


def cmd_get(args):
    connection = _connect_and_authenticate(args.file, args.id)
    logins = connection.get_logins(args.url) or []
    _emit_field(logins, args.field, args.all, "URL")


def cmd_get_by_path(args):
    connection = _connect_and_authenticate(args.file, args.id)

    try:
        response = connection.get_database_entries()
    except keepassxc_proxy_client.protocol.ResponseUnsuccesfulException as e:
        print(
            "error querying database entries: %s\n"
            "(this action requires \"Allow access to entries\" in KeePassXC's "
            "Browser Integration settings for the chosen association)" % e,
            file=sys.stderr,
        )
        sys.exit(1)

    target = _normalize_path(args.path)
    matches = [
        e for e in (response.get("entries") or [])
        if _normalize_path(_entry_full_path(e)) == target
    ]
    _emit_field(matches, args.field, args.all, "path")


def cmd_totp(args):
    connection = _connect_and_authenticate(args.file, args.id)

    totp = connection.get_totp(args.uuid)
    if not totp:
        print("No totp found for the given UUID", file=sys.stderr)
        sys.exit(1)

    print(totp)


def cmd_unlock(args):
    try:
        candidates = _load_for_use(args.file, args.id)
    except (FileNotFoundError, keystore.KeystoreError) as e:
        print("keystore error: %s" % e, file=sys.stderr)
        sys.exit(1)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    # For unlock we only use the first candidate, since the user-visible effect
    # (the unlock dialog) does not depend on which association we authenticate as.
    assoc_id, key_bytes = candidates[0]
    connection.load_associate(assoc_id, key_bytes)

    print(connection.test_associate(True))


def cmd_list(args):
    try:
        ids = keystore.list_associations(args.file)
    except (FileNotFoundError, keystore.KeystoreError) as e:
        print("keystore error: %s" % e, file=sys.stderr)
        sys.exit(1)

    for aid in ids:
        print(aid)
