import base64
import json
import sys

import keepassxc_proxy_client.protocol
from keepassxc_proxy_client import keystore


def _resolve_path(args):
    return args.file if args.file else keystore.default_path()


def _authenticate(connection, path):
    """Try every association stored at `path` until one authenticates.

    Returns True on success. Prints a diagnostic and returns False if the
    keystore is empty or no candidate authenticated.
    """
    ids = keystore.list_associations(path)
    if not ids:
        print("No associations stored in %s" % path)
        return False

    for assoc_id in ids:
        key_bytes = keystore.load(path, assoc_id)
        connection.load_associate(assoc_id, key_bytes)
        if connection.test_associate():
            return True

    print("None of the stored associations authenticated against the running KeePassXC instance")
    return False


def cmd_create(args):
    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.associate()

    if not connection.test_associate():
        print("For some reason the newly created association is invalid, this should not be happening")
        sys.exit(1)

    name, public_key = connection.dump_associate()
    out = {
        "version": keystore.SCHEMA_VERSION,
        "associations": {
            name: base64.b64encode(public_key).decode("ascii"),
        },
    }
    print(json.dumps(out))


def cmd_get(args):
    path = _resolve_path(args)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    if not _authenticate(connection, path):
        sys.exit(1)

    logins = connection.get_logins(args.url)
    if not logins:
        print("No logins found for the given URL")
        sys.exit(1)

    print(logins[0]["password"])


def cmd_totp(args):
    path = _resolve_path(args)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    if not _authenticate(connection, path):
        sys.exit(1)

    totp_value = connection.get_totp(args.uuid)
    if not totp_value:
        print("No totp found for the given UUID")
        sys.exit(1)

    print(totp_value)


def cmd_unlock(args):
    path = _resolve_path(args)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    if not _authenticate(connection, path):
        sys.exit(1)

    print(connection.test_associate(True))
