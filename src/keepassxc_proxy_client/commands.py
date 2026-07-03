import json
import sys

import keepassxc_proxy_client.protocol
from keepassxc_proxy_client import keystore


def create():
    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.associate()

    if not connection.test_associate():
        print("For some reason the newly created association is invalid, this should not be happening")
        return 1

    name, public_key = connection.dump_associate()
    print(json.dumps(keystore.dump_association(name, public_key)))
    return 0


def get(associate_file, url):
    name, public_key = keystore.load_association(associate_file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        return 1

    logins = connection.get_logins(url)
    if not logins:
        print("No logins found for the given URL")
        return 1

    print(logins[0]["password"])
    return 0


def totp(associate_file, uuid):
    name, public_key = keystore.load_association(associate_file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    if not connection.test_associate():
        print("The loaded association is invalid")
        return 1

    totp_value = connection.get_totp(uuid)
    if not totp_value:
        print("No totp found for the given UUID")
        return 1

    print(totp_value)
    return 0


def unlock(associate_file):
    name, public_key = keystore.load_association(associate_file)

    connection = keepassxc_proxy_client.protocol.Connection()
    connection.connect()
    connection.load_associate(name, public_key)

    print(connection.test_associate(True))
    return 0
