import sys
import json
import base64
import argparse

import keepassxc_proxy_client
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


def cmd_get(args):
    connection = _connect_and_authenticate(args.file, args.id)

    logins = connection.get_logins(args.url)
    if not logins:
        print("No logins found for the given URL", file=sys.stderr)
        sys.exit(1)

    entries = logins if args.all else logins[:1]

    if not args.all and len(logins) > 1:
        print(
            "warning: %d entries match this URL; printing the first. "
            "Pass --all to print every match." % len(logins),
            file=sys.stderr,
        )

    try:
        values = [_extract_field(e, args.field) for e in entries]
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(1)

    missing = [i for i, v in enumerate(values) if v is None]
    if missing:
        if len(entries) == 1:
            print(
                "field %r is not present on the matching entry" % args.field,
                file=sys.stderr,
            )
        else:
            print(
                "field %r is not present on %d of %d matching entries"
                % (args.field, len(missing), len(entries)),
                file=sys.stderr,
            )
        sys.exit(1)

    for v in values:
        print(v)


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


def _add_file_arg(p, default):
    p.add_argument(
        "--file",
        "-f",
        default=default,
        help="Path to the keystore JSON file. Defaults to %(default)s.",
    )


def _add_id_arg(p):
    p.add_argument(
        "--id",
        "-i",
        dest="id",
        default=None,
        help=(
            "Association id to use. If omitted, all stored associations are tried "
            "in turn until one authenticates successfully."
        ),
    )


def build_parser():
    default_keystore = keystore.default_path()
    parser = argparse.ArgumentParser(
        prog="keepassxc_proxy_client",
        description="Client for the KeePassXC Browser Integration protocol.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_create = sub.add_parser(
        "create",
        help="Create a new association with a running KeePassXC instance.",
        description=(
            "Connects to a locally running keepassxc instance and creates a new "
            "association (this will prompt a dialogue from KeePassXC). Without "
            "--save the association is printed to stdout as JSON. With --save it "
            "is persisted to the keystore file under the id returned by "
            "KeePassXC."
        ),
    )
    _add_file_arg(p_create, default_keystore)
    p_create.add_argument(
        "--save",
        "-s",
        action="store_true",
        help="Persist the new association to the keystore file instead of printing it.",
    )
    p_create.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing association with the same id (use with --save).",
    )
    p_create.set_defaults(func=cmd_create)

    p_get = sub.add_parser(
        "get",
        help="Get the first password for a URL.",
        description=(
            "Look up an entry by URL. If --file is omitted, the OS-default "
            "keystore is used. If --id is omitted, all stored associations are "
            "tried until one authenticates."
        ),
    )
    _add_file_arg(p_get, default_keystore)
    _add_id_arg(p_get)
    p_get.add_argument(
        "--field",
        "-F",
        default="password",
        help=(
            "Which entry field to print. One of: password (default), "
            "login/username, name/title, uuid, attr:<KEY> for a KeePassXC "
            "custom string attribute. Case-insensitive."
        ),
    )
    p_get.add_argument(
        "--all",
        "-a",
        action="store_true",
        help=(
            "Print the chosen field for every matching entry, one value per "
            "line. Default: print only the first match and emit a warning to "
            "stderr if more than one matched."
        ),
    )
    p_get.add_argument("url", help="URL to look up.")
    p_get.set_defaults(func=cmd_get)

    p_totp = sub.add_parser(
        "totp",
        help="Get the current TOTP for an entry UUID.",
        description=(
            "Fetch the current TOTP for an entry UUID. See `get` for keystore "
            "selection semantics."
        ),
    )
    _add_file_arg(p_totp, default_keystore)
    _add_id_arg(p_totp)
    p_totp.add_argument("uuid", help="Entry UUID.")
    p_totp.set_defaults(func=cmd_totp)

    p_unlock = sub.add_parser(
        "unlock",
        help="Ask a running KeePassXC to prompt the user to unlock a database.",
        description=(
            "Causes a running KeePassXC instance to launch a dialogue window to "
            "allow the user to unlock a locked database. If the database is "
            "already unlocked it has no effect."
        ),
    )
    _add_file_arg(p_unlock, default_keystore)
    _add_id_arg(p_unlock)
    p_unlock.set_defaults(func=cmd_unlock)

    p_list = sub.add_parser(
        "list",
        help="List association ids stored in the keystore.",
    )
    _add_file_arg(p_list, default_keystore)
    p_list.set_defaults(func=cmd_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
