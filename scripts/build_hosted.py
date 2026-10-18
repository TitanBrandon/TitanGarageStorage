"""Build the website image, optionally using this cloud's proxy and trust settings."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("--cloud-network", action="store_true")
parser.add_argument("--file", default="Dockerfile")
parser.add_argument("--tag", default="titan-space-studio:hosted")
args = parser.parse_args()
command = ["docker"]
if args.cloud_network:
    # Keep Docker's own cache/config in the writable workspace, without changing HOME.
    command += ["--config", "/workspace/.docker"]
command += ["build", "--progress=plain"]
if args.cloud_network:
    command += ["--network=host"]
    hosts = {}
    for name in ["HTTP_PROXY", "HTTPS_PROXY"]:
        hostname = urlsplit(os.environ.get(name, "")).hostname
        if hostname:
            hosts[hostname] = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
    for hostname, address in hosts.items():
        command += ["--add-host", hostname + ":" + address]
    for name in ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]:
        if name in os.environ:
            command += ["--build-arg", name]
    certificate = os.environ.get("SSL_CERT_FILE")
    if certificate:
        content = Path(certificate).read_bytes()
        if b"PRIVATE KEY" in content:
            raise SystemExit("The build trust bundle must contain public certificates only.")
        command += ["--secret", "id=build_ca,src=" + certificate]
command += ["--file", args.file, "--tag", args.tag, "."]
raise SystemExit(subprocess.call(command, cwd=Path(__file__).resolve().parents[1]))
