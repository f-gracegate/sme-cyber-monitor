"""Network primitives for monitoring, all with SSRF protection.

Every connection goes to an address we resolved and validated ourselves (public, routable),
with the original hostname sent in Host/SNI. Redirects are followed manually so each hop is
validated the same way. Bodies are never read beyond a few kilobytes.
"""

import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID

from app.services.verification import UnsafeTarget, resolve_public_addresses

USER_AGENT = "SMECM-Monitor/1.0 (+security monitoring; authorised by the site owner)"
_MAX_BODY = 4096


@dataclass
class Response:
    url: str
    status_code: int
    headers: list[tuple[str, str]]
    elapsed_ms: int
    peer_ip: str

    def header(self, name: str) -> str | None:
        name = name.lower()
        for k, v in self.headers:
            if k.lower() == name:
                return v
        return None

    def header_all(self, name: str) -> list[str]:
        name = name.lower()
        return [v for k, v in self.headers if k.lower() == name]


@dataclass
class FetchResult:
    ok: bool
    final: Response | None = None
    chain: list[Response] = field(default_factory=list)
    error: str | None = None
    unsafe: bool = False


def _request(url: str, timeout: float) -> Response:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeTarget(f"Refusing to fetch {url!r}")
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    ip = resolve_public_addresses(host)[0]
    ip_host = f"[{ip}]" if ":" in ip else ip
    path = parts.path or "/"
    if parts.query:
        path += f"?{parts.query}"
    target = f"{parts.scheme}://{ip_host}:{port}{path}"
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
    host_header = host if port in {80, 443} else f"{host}:{port}"
    started = time.monotonic()
    with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False) as client:
        with client.stream(
            "GET",
            target,
            headers={"Host": host_header, "User-Agent": USER_AGENT, "Accept": "*/*"},
            extensions=extensions,
        ) as resp:
            read = 0
            for chunk in resp.iter_bytes():
                read += len(chunk)
                if read >= _MAX_BODY:
                    break
            elapsed = int((time.monotonic() - started) * 1000)
            return Response(
                url=url,
                status_code=resp.status_code,
                headers=list(resp.headers.multi_items()),
                elapsed_ms=elapsed,
                peer_ip=ip,
            )


def fetch(
    url: str, *, follow_redirects: bool = True, max_redirects: int = 5, timeout: float = 10.0
) -> FetchResult:
    chain: list[Response] = []
    current = url
    try:
        for _ in range(max_redirects + 1):
            resp = _request(current, timeout)
            chain.append(resp)
            location = resp.header("location")
            if follow_redirects and resp.status_code in {301, 302, 303, 307, 308} and location:
                current = urljoin(current, location)
                continue
            return FetchResult(ok=True, final=resp, chain=chain)
        return FetchResult(ok=False, chain=chain, error="Too many redirects")
    except UnsafeTarget as exc:
        return FetchResult(ok=False, chain=chain, error=str(exc), unsafe=True)
    except httpx.TimeoutException:
        return FetchResult(ok=False, chain=chain, error="Timed out waiting for a response")
    except httpx.ConnectError as exc:
        return FetchResult(ok=False, chain=chain, error=_connect_reason(exc))
    except httpx.HTTPError as exc:
        return FetchResult(ok=False, chain=chain, error=f"{type(exc).__name__}: {exc}"[:200])


def _connect_reason(exc: Exception) -> str:
    text = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return "TLS certificate could not be verified"
    if "refused" in text.lower():
        return "Connection refused"
    return "Could not connect"[:200]


# --- TLS ------------------------------------------------------------------------------------


@dataclass
class CertificateInfo:
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    sans: list[str]
    self_signed: bool

    @property
    def days_left(self) -> int:
        return int((self.not_after - datetime.now(UTC)).total_seconds() // 86400)


@dataclass
class TLSProbe:
    reachable: bool
    error: str | None = None
    trusted: bool = False
    trust_error: str | None = None
    protocol: str | None = None
    certificate: CertificateInfo | None = None
    legacy_protocols: list[str] = field(default_factory=list)
    legacy_tested: bool = False
    peer_ip: str | None = None


def _cn(name: x509.Name) -> str:
    attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME) or name.get_attributes_for_oid(
        NameOID.ORGANIZATION_NAME
    )
    return str(attrs[0].value) if attrs else name.rfc4514_string()


def parse_certificate(der: bytes) -> CertificateInfo:
    cert = x509.load_der_x509_certificate(der)
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = san_ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        sans = []
    return CertificateInfo(
        subject=_cn(cert.subject),
        issuer=_cn(cert.issuer),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        sans=list(sans)[:20],
        self_signed=cert.issuer == cert.subject,
    )


def _handshake(ip: str, host: str, ctx: ssl.SSLContext, timeout: float):
    sock = socket.create_connection((ip, 443), timeout=timeout)
    try:
        tls = ctx.wrap_socket(sock, server_hostname=host)
    except Exception:
        sock.close()
        raise
    return tls


def probe_tls(host: str, timeout: float = 8.0) -> TLSProbe:
    try:
        ip = resolve_public_addresses(host)[0]
    except UnsafeTarget as exc:
        return TLSProbe(reachable=False, error=str(exc))

    result = TLSProbe(reachable=False, peer_ip=ip)
    try:
        with _handshake(ip, host, ssl.create_default_context(), timeout) as tls:
            result.reachable = result.trusted = True
            result.protocol = tls.version()
            der = tls.getpeercert(binary_form=True)
            if der:
                result.certificate = parse_certificate(der)
    except ssl.SSLCertVerificationError as exc:
        result.reachable = True
        result.trust_error = exc.verify_message or str(exc)
    except (TimeoutError, ConnectionRefusedError, OSError, ssl.SSLError) as exc:
        result.error = (
            "Connection refused"
            if isinstance(exc, ConnectionRefusedError)
            else ("Timed out" if isinstance(exc, TimeoutError) else f"{type(exc).__name__}")
        )
        return result

    if result.certificate is None:
        # Untrusted: fetch the certificate anyway (without trusting it) to describe it.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with _handshake(ip, host, ctx, timeout) as tls:
                result.protocol = tls.version()
                der = tls.getpeercert(binary_form=True)
                if der:
                    result.certificate = parse_certificate(der)
        except (OSError, ssl.SSLError):
            pass

    result.legacy_protocols, result.legacy_tested = _legacy_protocols(ip, host, timeout)
    return result


def _legacy_protocols(ip: str, host: str, timeout: float) -> tuple[list[str], bool]:
    """Try TLS 1.0 and 1.1. Returns ([] , False) if this machine's OpenSSL can't test them."""
    accepted: list[str] = []
    tested = False
    for name, version in (("TLSv1", ssl.TLSVersion.TLSv1), ("TLSv1.1", ssl.TLSVersion.TLSv1_1)):
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = version
            ctx.maximum_version = version
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except (ValueError, ssl.SSLError):
            continue
        try:
            with _handshake(ip, host, ctx, timeout):
                accepted.append(name)
            tested = True
        except ssl.SSLError as exc:
            # "no protocols available" means our side can't speak it: not a server verdict.
            if "NO_PROTOCOLS_AVAILABLE" not in str(exc).upper():
                tested = True
        except OSError:
            continue
    return accepted, tested
