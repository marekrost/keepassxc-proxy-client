import argparse
import sys
import traceback

from keepassxc_proxy_client import keystore
from keepassxc_proxy_client import commands
from keepassxc_proxy_client.errors import ProxyClientError


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


def _add_field_and_all_args(p):
    p.add_argument(
        "--field",
        "-F",
        default="password",
        help=(
            "Which entry field to print. One of: password (default), "
            "login/username, name/title, uuid, attr:<KEY> for a KeePassXC "
            "custom string attribute. Case-insensitive."
        ),
    )
    p.add_argument(
        "--all",
        "-a",
        action="store_true",
        help=(
            "Print the chosen field for every matching entry, one value per "
            "line. Default: print only the first match and emit a warning to "
            "stderr if more than one matched."
        ),
    )


def build_parser():
    default_keystore = keystore.default_path()
    parser = argparse.ArgumentParser(
        prog="keepassxc_proxy_client",
        description="Client for the KeePassXC Browser Integration protocol.",
    )
    parser.add_argument(
        "--socket",
        default=None,
        metavar="PATH",
        help=(
            "Override the auto-detected KeePassXC Browser Integration socket "
            "path. Default detection follows Connection.get_socket_path()."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print Python tracebacks on error in addition to the one-line message.",
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
    p_create.set_defaults(func=commands.cmd_create)

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
    _add_field_and_all_args(p_get)
    p_get.add_argument("url", help="URL to look up.")
    p_get.set_defaults(func=commands.cmd_get)

    p_gbp = sub.add_parser(
        "get-by-path",
        help="Get an entry by its location in the database tree.",
        description=(
            "Look up an entry by its group/title path within the database. "
            "Requires \"Allow access to entries\" enabled for the chosen "
            "association in KeePassXC's Browser Integration settings. "
            "Unlike `get`, this returns metadata from the full database tree "
            "(scoped to what the association is permitted to see), not just "
            "URL-keyed lookups."
        ),
    )
    _add_file_arg(p_gbp, default_keystore)
    _add_id_arg(p_gbp)
    _add_field_and_all_args(p_gbp)
    p_gbp.add_argument(
        "path",
        help=(
            "Slash-separated entry path: group/subgroup/.../title. Leading "
            "slash is optional. Case-sensitive."
        ),
    )
    p_gbp.set_defaults(func=commands.cmd_get_by_path)

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
    p_totp.set_defaults(func=commands.cmd_totp)

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
    p_unlock.set_defaults(func=commands.cmd_unlock)

    p_list = sub.add_parser(
        "list",
        help="List association ids stored in the keystore.",
    )
    _add_file_arg(p_list, default_keystore)
    p_list.set_defaults(func=commands.cmd_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ProxyClientError as e:
        print(str(e), file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        sys.exit(e.exit_code)
    except Exception:
        # Unanticipated failure — always print the traceback. argparse exits
        # for its own errors before we get here.
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
