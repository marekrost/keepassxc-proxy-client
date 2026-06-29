import sys
import json
import base64
import argparse

import keepassxc_proxy_client
import keepassxc_proxy_client.protocol


def _load_association(path):
    with open(path, "r") as f:
        association = json.load(f)
    return association["name"], base64.b64decode(association["public_key"].encode("utf-8"))


def cmd_create(args):
    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.associate()

    if not connection.test_associate():
        print("For some reason the newly created association is invalid, this should not be happening")
        sys.exit(1)

    name, public_key = connection.dump_associate()
    out = {
        "name": name,
        "public_key": base64.b64encode(public_key).decode("utf-8"),
    }
    print(json.dumps(out))


def cmd_get(args):
    name, public_key = _load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        sys.exit(1)

    logins = connection.get_logins(args.url)
    if not logins:
        print("No logins found for the given URL")
        sys.exit(1)

    print(logins[0]["password"])


def cmd_totp(args):
    name, public_key = _load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        sys.exit(1)

    totp = connection.get_totp(args.uuid)
    if not totp:
        print("No totp found for the given UUID")
        sys.exit(1)

    print(totp)


def cmd_unlock(args):
    name, public_key = _load_association(args.file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    print(connection.test_associate(True))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="keepassxc_proxy_client",
        description="Client for the KeePassXC Browser Integration protocol.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_create = sub.add_parser(
        "create",
        help="Create a new association with a running KeePassXC instance.",
        description=(
            "Connects to a locally running keepassxc instance, creates a new "
            "association with it (this will prompt a dialogue from keepassxc) "
            "and prints it to stdout as JSON. Note that the public key that is "
            "printed is secret and can allow anyone with access to your local "
            "machine access to all passwords that are related to a URL, thus it "
            "should be stored safely."
        ),
    )
    p_create.set_defaults(func=cmd_create)

    p_get = sub.add_parser(
        "get",
        help="Get the first password for a URL.",
        description=(
            "Reads a keepassxc association from <file> and attempts to get the "
            "first password for <url>. Will exit with 1 if the association is "
            "not valid for the running keepassxc instance or no logins are "
            "found for the given URL."
        ),
    )
    p_get.add_argument("file", help="Path to the association JSON file.")
    p_get.add_argument("url", help="URL to look up.")
    p_get.set_defaults(func=cmd_get)

    p_totp = sub.add_parser(
        "totp",
        help="Get the current TOTP for an entry UUID.",
        description=(
            "Reads a keepassxc association from <file> and attempts to get the "
            "current totp for <uuid>. Will exit with 1 if the association is "
            "not valid for the running keepassxc instance or no totp is found "
            "for the given UUID."
        ),
    )
    p_totp.add_argument("file", help="Path to the association JSON file.")
    p_totp.add_argument("uuid", help="Entry UUID.")
    p_totp.set_defaults(func=cmd_totp)

    p_unlock = sub.add_parser(
        "unlock",
        help="Ask a running KeePassXC to prompt the user to unlock a database.",
        description=(
            "Causes a running KeepassXC instance to launch a dialogue window to "
            "allow the user to unlock a locked database. If the database is "
            "already unlocked it has no effect."
        ),
    )
    p_unlock.add_argument("file", help="Path to the association JSON file.")
    p_unlock.set_defaults(func=cmd_unlock)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
