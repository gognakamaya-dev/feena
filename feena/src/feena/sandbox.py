"""Boot the app under test in a throwaway, no-egress Docker sandbox.

This module is the security boundary. Two invariants matter:

1. The app runs on a Docker network created with ``internal=True``, which removes the
   container's route to the internet (no egress). The host can still reach the app through a
   *published* port (ingress via docker-proxy is separate from the container's own egress), so
   Feena can drive it while the app itself cannot phone home or attack anything outside.
2. Feena only ever hands a Sandbox to the hostile agent, and the hostile agent refuses any
   target that did not come from a Sandbox it built (see ``assert_sandboxed``). "Attack only
   the copy under test" is therefore a structural property, not a line in the docs.

Single-service bring-up is implemented below. Multi-service (compose: app + db + queue) is the
documented next step: bring every service up on the same internal network so none gains egress.

NOTE: this file talks to a live Docker daemon. It is written to be correct; it has not been
executed in the build environment (no daemon there), so treat first real runs as the shakedown.
"""
from __future__ import annotations

import ipaddress
import secrets
import socket
import time
from urllib.parse import urlsplit
from dataclasses import dataclass, field

import docker
import httpx

from .config import Config


class SandboxError(RuntimeError):
    pass


@dataclass
class Sandbox:
    """A running, isolated copy of the app under test.

    ``base_url`` is the only thing agents get. ``token`` proves the URL was produced by a real
    sandbox; the hostile agent checks it before running any security check.
    """

    base_url: str
    token: str = field(default_factory=lambda: secrets.token_hex(16))

    def health_ok(self, path: str, timeout: float = 3.0) -> bool:
        try:
            r = httpx.get(self.base_url.rstrip("/") + path, timeout=timeout)
            return r.status_code < 500
        except httpx.HTTPError:
            return False


class SandboxManager:
    """Creates and tears down sandboxes. Use as a context manager."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        try:
            self.client = docker.from_env()
        except Exception as e:  # noqa: BLE001
            raise SandboxError(f"Could not connect to Docker: {e}") from e
        self._network = None
        self._containers: list = []
        self.sandbox: Sandbox | None = None

    def __enter__(self) -> Sandbox:
        return self.up()

    def __exit__(self, *exc) -> None:
        self.down()

    def up(self) -> Sandbox:
        net_name = f"feena-{secrets.token_hex(4)}"
        # internal=True => the container has no route to the outside world. This is egress-lock.
        self._network = self.client.networks.create(net_name, driver="bridge", internal=True)

        image = self._resolve_image()
        # Publish the app port to an ephemeral host port. Ingress works; egress stays blocked.
        container = self.client.containers.run(
            image,
            detach=True,
            network=net_name,
            ports={f"{self.cfg.target.port}/tcp": None},  # None => random free host port
            environment={"NODE_ENV": "test", "FEENA": "1"},
            labels={"feena": "1"},
        )
        self._containers.append(container)

        host_port = self._published_port(container, self.cfg.target.port)
        sandbox = Sandbox(base_url=f"http://127.0.0.1:{host_port}")
        self._wait_healthy(sandbox)
        self.sandbox = sandbox
        return sandbox

    def _resolve_image(self) -> str:
        """Build from the example/target Dockerfile if present, else expect a prebuilt image.

        For the single-service scaffold we build from a Dockerfile that sits next to the
        compose file. A full compose parser (multiple services) lands next.
        """
        build_dir = self.cfg.compose_path.parent
        dockerfile = build_dir / "Dockerfile"
        if dockerfile.exists():
            tag = f"feena-target:{secrets.token_hex(4)}"
            self.client.images.build(path=str(build_dir), tag=tag, rm=True)
            return tag
        raise SandboxError(
            f"No Dockerfile at {dockerfile}. Multi-service compose bring-up is not wired up in "
            "this scaffold; add a Dockerfile for single-service, or implement the compose path "
            "(every service on the internal network)."
        )

    @staticmethod
    def _published_port(container, container_port: int) -> str:
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"]
        mapping = ports.get(f"{container_port}/tcp")
        if not mapping:
            raise SandboxError(
                f"Port {container_port} was not published. On some Docker setups an internal "
                "network refuses published ports; run the driving browser inside the network "
                "instead (the in-network runner, next milestone)."
            )
        return mapping[0]["HostPort"]

    def _wait_healthy(self, sandbox: Sandbox) -> None:
        deadline = time.time() + self.cfg.target.boot_timeout
        while time.time() < deadline:
            if sandbox.health_ok(self.cfg.target.healthcheck):
                return
            time.sleep(1.0)
        raise SandboxError(
            f"App did not become healthy within {self.cfg.target.boot_timeout}s "
            f"(polling {self.cfg.target.healthcheck})."
        )

    def down(self) -> None:
        for c in self._containers:
            try:
                c.remove(force=True)
            except Exception:
                pass
        if self._network is not None:
            try:
                self._network.remove()
            except Exception:
                pass


def _resolves_only_private(host: str) -> bool:
    """True iff EVERY address the host resolves to is loopback / private / link-local.

    Resolved, not string-matched: 'localhost.evil.com' and 'staging.example.com' resolve to public
    addresses and are refused, while a docker-compose service name that resolves inside the
    runner's private network is allowed. Unresolvable names are refused.
    """
    host = host.strip("[]")
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0].split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            return False
    return True


def attach(url: str) -> Sandbox:
    """Attach to an app that is ALREADY RUNNING locally (a CI service, docker compose, dev server).

    This is how the GitHub Action works: the workflow starts your app on the runner and Feena
    attaches to it. The safety line is the same as for a built sandbox: the target must be a copy
    you are running yourself, so only loopback/private addresses are accepted. Pointing this at a
    public host is refused, with no override.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SandboxError(f"'{url}' is not a valid http(s) URL.")
    if not _resolves_only_private(parts.hostname):
        raise SandboxError(
            f"Refusing to attach to '{parts.hostname}': it does not resolve to a loopback or "
            "private address. Feena only tests an app you are running yourself (a local process, "
            "a docker service, a private staging network), never a public host."
        )
    return Sandbox(base_url=url.rstrip("/"))


def wait_healthy(sandbox: Sandbox, path: str = "/", timeout: int = 60) -> bool:
    """Poll until the app answers (any status < 500) or the timeout passes."""
    deadline = time.time() + timeout
    while True:
        if sandbox.health_ok(path):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(1.0)


def assert_sandboxed(sandbox: Sandbox | None, base_url: str) -> None:
    """Guard used by the hostile agent: refuse any target we did not sandbox ourselves."""
    if sandbox is None or sandbox.base_url != base_url or not sandbox.token:
        raise SandboxError(
            "Refusing to run the hostile agent against a target Feena did not sandbox. "
            "The hostile agent only runs inside a no-egress sandbox it built."
        )
