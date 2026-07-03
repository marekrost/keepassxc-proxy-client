import base64
import json


def load_association(path):
    data = json.load(open(path, "r"))
    return data["name"], base64.b64decode(data["public_key"].encode("utf-8"))


def dump_association(name, public_key):
    return {
        "name": name,
        "public_key": base64.b64encode(public_key).decode("utf-8"),
    }
