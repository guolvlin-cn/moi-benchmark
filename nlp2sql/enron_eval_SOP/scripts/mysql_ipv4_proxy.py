#!/usr/bin/env python3
"""Bridge Docker Desktop IPv4 connections to a host IPv6 MySQL listener."""

from __future__ import annotations

import argparse
import selectors
import socket
import threading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind-host", default="127.0.0.1")
    parser.add_argument("--bind-port", type=int, default=13306)
    parser.add_argument("--target-host", default="::1")
    parser.add_argument("--target-port", type=int, default=3306)
    return parser.parse_args()


def relay(client: socket.socket, target_host: str, target_port: int) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=10)
        client.setblocking(False)
        upstream.setblocking(False)
        selector = selectors.DefaultSelector()
        selector.register(client, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, client)
        while True:
            for key, _ in selector.select():
                source = key.fileobj
                destination = key.data
                data = source.recv(65536)
                if not data:
                    return
                destination.sendall(data)
    except (ConnectionError, OSError):
        return
    finally:
        client.close()
        if upstream is not None:
            upstream.close()


def main() -> None:
    args = parse_args()
    family = socket.AF_INET6 if ":" in args.bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.bind_host, args.bind_port))
        server.listen()
        print(
            f"MySQL bridge listening on {args.bind_host}:{args.bind_port} "
            f"-> {args.target_host}:{args.target_port}",
            flush=True,
        )
        while True:
            client, _ = server.accept()
            threading.Thread(
                target=relay,
                args=(client, args.target_host, args.target_port),
                daemon=True,
            ).start()


if __name__ == "__main__":
    main()
