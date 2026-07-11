import argparse

from keepassxc_proxy_client import commands


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
            "Connects to a locally running keepassxc instance and creates a new "
            "association (this will prompt a dialogue from KeePassXC). The "
            "association is printed to stdout as JSON. Note that the public key "
            "printed is secret and should be stored safely."
        ),
    )
    p_create.set_defaults(func=commands.cmd_create)

    p_get = sub.add_parser(
        "get",
        help="Get the first password for an entry matched by URL.",
        description=(
            "Reads a keepassxc association from <file> and attempts to get the "
            "first password for <url>. Exits with 1 if the association is not "
            "valid for the running keepassxc instance or no logins are found."
        ),
    )
    p_get.add_argument("file", help="Path to the association JSON file.")
    p_get.add_argument("url", help="URL to look up.")
    p_get.set_defaults(func=commands.cmd_get)

    p_totp = sub.add_parser(
        "totp",
        help="Get the current TOTP for an entry UUID.",
        description=(
            "Reads a keepassxc association from <file> and attempts to get the "
            "current TOTP for <uuid>. Exits with 1 if the association is not "
            "valid for the running keepassxc instance or no TOTP is found."
        ),
    )
    p_totp.add_argument("file", help="Path to the association JSON file.")
    p_totp.add_argument("uuid", help="Entry UUID.")
    p_totp.set_defaults(func=commands.cmd_totp)

    p_unlock = sub.add_parser(
        "unlock",
        help="Ask KeePassXC to prompt the user to unlock a database.",
        description=(
            "Causes a running KeePassXC instance to launch a dialogue window to "
            "allow the user to unlock a locked database. If the database is "
            "already unlocked it has no effect."
        ),
    )
    p_unlock.add_argument("file", help="Path to the association JSON file.")
    p_unlock.set_defaults(func=commands.cmd_unlock)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
