"""Proof that an organisation controls a website or domain before we monitor it.

Outbound checks are a classic server-side request forgery (SSRF) risk: a customer could register
"internal.example" pointing at 169.254.169.254 or a private service. The HTTP check therefore:

* resolves the hostname once and refuses any address that is not globally routable,
* connects to that exact, already-validated IP (no second DNS lookup, so no rebinding),
  while sending the original Host header and TLS SNI so certificates still verify,
* never follows redirects, uses short timeouts and reads at most 1 KB.
"""

import ipaddress
import secrets
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import dns.exception
import dns.resolver
import httpx

from app.core.config import settings
from app.models import Asset

CHALLENGE_PREFIX = "smecm-verification="
DNS_LABEL = "_smecm-challenge"
HTTP_PATH = "/.well-known/smecm-verification.txt"
_MAX_BODY = 1024


class UnsafeTarget(Exception):
    pass


@dataclass
class CheckResult:
    ok: bool
    detail: str
    evidence: dict


def new_challenge() -> str:
    return secrets.token_hex(16)


def asset_hostname(asset: Asset) -> str:
    if asset.type == "website":
        return urlsplit(asset.identifier).hostname or ""
    return asset.identifier


def dns_record_name(host: str) -> str:
    return f"{DNS_LABEL}.{host}"


def expected_value(challenge: str) -> str:
    return CHALLENGE_PREFIX + challenge


def _is_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if settings.allow_private_verification_targets:
        return not (ip.is_unspecified or ip.is_multicast)
    return ip.is_global and not ip.is_multicast


def resolve_public_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeTarget(f"{host} could not be resolved.") from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise UnsafeTarget(f"{host} could not be resolved.")
    for addr in addresses:
        if not _is_allowed(ipaddress.ip_address(addr.split("%")[0])):
            raise UnsafeTarget(
                f"{host} resolves to a private or reserved address ({addr}). "
                "Only publicly reachable websites can be verified this way."
            )
    return addresses


def check_dns_txt(host: str, challenge: str) -> CheckResult:
    name = dns_record_name(host)
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 6
    try:
        answers = resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return CheckResult(
            False,
            f"No TXT record found at {name} yet. DNS changes can take a few minutes to appear.",
            {"record_name": name},
        )
    except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
        return CheckResult(
            False,
            f"DNS lookup for {name} failed. Try again shortly.",
            {"record_name": name, "error": type(exc).__name__},
        )
    values = [b"".join(r.strings).decode("utf-8", errors="replace") for r in answers]
    found = expected_value(challenge) in values
    return CheckResult(
        found,
        "TXT record matched."
        if found
        else f"A TXT record exists at {name} but the value does "
        "not match. Check you copied it exactly.",
        {"record_name": name, "values_seen": values[:5]},
    )


def check_http_file(host: str, challenge: str) -> CheckResult:
    try:
        addresses = resolve_public_addresses(host)
    except UnsafeTarget as exc:
        return CheckResult(False, str(exc), {"host": host})
    ip = addresses[0]
    url_host = f"[{ip}]" if ":" in ip else ip
    url = f"https://{url_host}{HTTP_PATH}"
    evidence = {"url": f"https://{host}{HTTP_PATH}", "connected_ip": ip}
    try:
        with httpx.Client(timeout=httpx.Timeout(6.0), follow_redirects=False) as client:
            with client.stream(
                "GET",
                url,
                headers={"Host": host, "User-Agent": "SMECM-Verifier/1.0"},
                extensions={"sni_hostname": host},
            ) as response:
                evidence["status_code"] = response.status_code
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > _MAX_BODY:
                        break
    except httpx.HTTPError as exc:
        return CheckResult(
            False,
            f"Could not fetch https://{host}{HTTP_PATH} "
            f"({type(exc).__name__}). Check the file is published over HTTPS.",
            evidence,
        )
    if response.status_code != 200:
        return CheckResult(
            False,
            f"https://{host}{HTTP_PATH} returned HTTP {response.status_code}; expected 200.",
            evidence,
        )
    text = body[:_MAX_BODY].decode("utf-8", errors="replace").strip()
    ok = text == expected_value(challenge)
    return CheckResult(
        ok,
        "Verification file matched."
        if ok
        else "The verification file was found but its contents do not match.",
        evidence,
    )


def instructions(asset: Asset, method: str, challenge: str) -> dict:
    host = asset_hostname(asset)
    if method == "dns_txt":
        return {
            "method": method,
            "summary": "Add a DNS TXT record to prove you control this domain.",
            "steps": [
                "Sign in to the company that manages your domain's DNS "
                "(your registrar or hosting provider).",
                "Create a new TXT record with the name and value below.",
                "Save it, wait a few minutes, then select Check verification.",
            ],
            "record_name": dns_record_name(host),
            "record_value": expected_value(challenge),
        }
    if method == "http_file":
        return {
            "method": method,
            "summary": "Publish a small text file on your website to prove you control it.",
            "steps": [
                "Create a plain text file containing exactly the value below.",
                f"Publish it so it opens at https://{host}{HTTP_PATH}",
                "Then select Check verification.",
            ],
            "file_url": f"https://{host}{HTTP_PATH}",
            "file_contents": expected_value(challenge),
        }
    return {
        "method": method,
        "summary": "An administrator confirmed the organisation owns or is authorised to "
        "monitor this asset.",
        "steps": [],
    }
