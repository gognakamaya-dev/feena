"""Standalone export helpers: no Feena installation required."""
import ipaddress
import os
import socket
from types import SimpleNamespace
from urllib.parse import urlsplit


def local_url(value):
    parts = urlsplit(value)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or parts.path not in ("", "/")):
        raise ValueError("Set an http(s) origin for a disposable local/private service")
    addresses = socket.getaddrinfo(parts.hostname, parts.port)
    if not addresses or any(not (ipaddress.ip_address(a[4][0].split("%")[0]).is_private
                                or ipaddress.ip_address(a[4][0].split("%")[0]).is_loopback)
                            for a in addresses):
        raise ValueError("Tests require a local/private service")
    return value.rstrip("/")


def base_url():
    return local_url(os.environ["FEENA_BASE_URL"])


def _local_path(value):
    parts = urlsplit(value)
    if (not value.startswith("/") or value.startswith("//") or "\\" in value
            or parts.scheme or parts.netloc or parts.fragment
            or any(ord(c) < 32 for c in value)):
        raise ValueError("Expected a target-relative path")
    return value


def _contains(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items())
    return type(actual) is type(expected) and actual == expected


class Spec(SimpleNamespace):
    def model_dump(self, **kwargs):
        def plain(value):
            if isinstance(value, Spec):
                return {k: plain(v) for k, v in vars(value).items()}
            if isinstance(value, list):
                return [plain(v) for v in value]
            return value
        return plain(self)


def spec(value):
    if isinstance(value, dict):
        return Spec(**{k: spec(v) if k not in ("expected", "json_body") else v
                       for k, v in value.items()})
    if isinstance(value, list):
        return [spec(v) for v in value]
    return value
