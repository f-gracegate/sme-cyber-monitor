"""Check implementations.

Each check has two halves: a *collector* that talks to the network and an *evaluator* that turns
what was collected into a status, summary and list of issues. Evaluators are pure functions, so
the rules are unit-tested without touching the internet.
"""

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import dns.exception
import dns.resolver

from app.monitoring import net

SLOW_MS = 5000
HSTS_MIN_SECONDS = 15552000  # 6 months


@dataclass
class Issue:
    rule_key: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Outcome:
    # ok | warning (issues found) | failing (asset is down) | error (we couldn't check)
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    # True when the asset answered (used for "last seen").
    reachable: bool = False

    @property
    def evaluated(self) -> bool:
        """Only a completed evaluation may clear findings. Missing data never improves a score."""
        return self.status != "error"


def _with_issues(outcome: Outcome) -> Outcome:
    if outcome.status == "ok" and outcome.issues:
        outcome.status = "warning"
    return outcome


# --- Uptime ---------------------------------------------------------------------------------


def evaluate_uptime(result: net.FetchResult, previous_failures: int) -> Outcome:
    if result.unsafe:
        return Outcome(
            "error", result.error or "Address is not publicly reachable", {"error": result.error}
        )
    if not result.ok or result.final is None:
        failures = previous_failures + 1
        issues = [Issue("website_unreachable", {"error": result.error, "consecutive": failures})]
        return Outcome(
            "failing",
            f"Not responding: {result.error or 'no response'}",
            {"error": result.error, "consecutive_failures": failures},
            issues if failures >= 2 else [],
        )
    final = result.final
    data = {
        "status_code": final.status_code,
        "response_ms": final.elapsed_ms,
        "final_url": final.url,
        "redirects": len(result.chain) - 1,
        "ip": final.peer_ip,
    }
    if final.status_code >= 500:
        failures = previous_failures + 1
        data["consecutive_failures"] = failures
        return Outcome(
            "failing",
            f"Server error (HTTP {final.status_code})",
            data,
            [Issue("website_server_error", {"status_code": final.status_code})]
            if failures >= 2
            else [],
            reachable=True,
        )
    issues = []
    if final.elapsed_ms > SLOW_MS:
        issues.append(Issue("website_slow", {"response_ms": final.elapsed_ms}))
    return _with_issues(
        Outcome(
            "ok",
            f"Up · HTTP {final.status_code} in {final.elapsed_ms} ms",
            data,
            issues,
            reachable=True,
        )
    )


def run_uptime(url: str, previous_failures: int) -> Outcome:
    return evaluate_uptime(net.fetch(url), previous_failures)


# --- Security headers -----------------------------------------------------------------------


def _hsts_max_age(value: str) -> int | None:
    match = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.I)
    return int(match.group(1)) if match else None


def evaluate_headers(https: net.FetchResult, http: net.FetchResult | None) -> Outcome:
    if not https.ok or https.final is None:
        return Outcome(
            "error", f"Could not load the website: {https.error}", {"error": https.error}
        )
    resp = https.final
    issues: list[Issue] = []
    present = {k.lower() for k, _ in resp.headers}
    data: dict[str, Any] = {"final_url": resp.url, "headers_present": sorted(present)}

    if http is not None and http.ok and http.chain:
        first = http.chain[0]
        location = first.header("location") or ""
        redirected = first.status_code in {301, 302, 307, 308} and location.startswith("https://")
        data["http_redirects_to_https"] = redirected
        if not redirected:
            issues.append(
                Issue(
                    "http_not_redirected",
                    {"status_code": first.status_code, "location": location or None},
                )
            )

    hsts = resp.header("strict-transport-security")
    if not hsts:
        issues.append(Issue("missing_hsts"))
    else:
        age = _hsts_max_age(hsts)
        if age is None or age < HSTS_MIN_SECONDS:
            issues.append(Issue("weak_hsts", {"header": hsts[:200]}))

    csp = resp.header("content-security-policy")
    if not csp:
        issues.append(Issue("missing_csp"))
    if (resp.header("x-content-type-options") or "").strip().lower() != "nosniff":
        issues.append(Issue("missing_nosniff"))
    if not resp.header("x-frame-options") and "frame-ancestors" not in (csp or "").lower():
        issues.append(Issue("missing_clickjacking_protection"))
    if not resp.header("referrer-policy"):
        issues.append(Issue("missing_referrer_policy"))

    server = resp.header("server")
    if server and re.search(r"\d", server):
        issues.append(Issue("server_version_disclosed", {"server": server[:120]}))
    powered = resp.header("x-powered-by")
    if powered:
        issues.append(Issue("technology_disclosed", {"x_powered_by": powered[:120]}))

    weak_cookies = []
    for cookie in resp.header_all("set-cookie"):
        name = cookie.split("=", 1)[0].strip()
        flags = cookie.lower()
        missing = [f for f in ("secure", "httponly") if f not in flags]
        if missing:
            weak_cookies.append({"name": name[:60], "missing": missing})
    if weak_cookies:
        issues.append(Issue("insecure_cookies", {"cookies": weak_cookies[:10]}))

    n = len(issues)
    return _with_issues(
        Outcome(
            "ok",
            "All recommended headers present" if n == 0 else f"{n} header issue(s) found",
            data,
            issues,
            reachable=True,
        )
    )


def run_security_headers(url: str) -> Outcome:
    host = urlsplit(url).hostname or ""
    https = net.fetch(f"https://{host}/")
    if not https.ok and not https.unsafe:
        https = net.fetch(f"https://{host}/")  # one retry: a single network blip isn't a result
    http = net.fetch(f"http://{host}/", follow_redirects=False)
    return evaluate_headers(https, http)


# --- TLS ------------------------------------------------------------------------------------


def evaluate_tls(probe: net.TLSProbe) -> Outcome:
    if not probe.reachable:
        if probe.error in {"Connection refused", "Timed out"}:
            return Outcome(
                "warning",
                f"HTTPS not available ({probe.error.lower()})",
                {"error": probe.error},
                [Issue("https_unavailable", {"error": probe.error})],
            )
        return Outcome("error", f"Could not check TLS: {probe.error}", {"error": probe.error})

    issues: list[Issue] = []
    cert = probe.certificate
    data: dict[str, Any] = {
        "protocol": probe.protocol,
        "trusted": probe.trusted,
        "ip": probe.peer_ip,
    }
    if cert:
        data.update(
            {
                "subject": cert.subject,
                "issuer": cert.issuer,
                "expires_at": cert.not_after.isoformat(),
                "days_left": cert.days_left,
                "sans": cert.sans,
            }
        )
        if cert.days_left < 0:
            issues.append(
                Issue("tls_certificate_expired", {"expired_on": cert.not_after.date().isoformat()})
            )
        elif cert.days_left <= 14:
            issues.append(Issue("tls_certificate_expiring_14d", {"days_left": cert.days_left}))
        elif cert.days_left <= 30:
            issues.append(Issue("tls_certificate_expiring_30d", {"days_left": cert.days_left}))
    if not probe.trusted and not (cert and cert.days_left < 0):
        issues.append(Issue("tls_certificate_invalid", {"reason": probe.trust_error}))
    if probe.legacy_protocols:
        issues.append(Issue("tls_legacy_protocol", {"accepted": probe.legacy_protocols}))
    data["legacy_protocols_tested"] = probe.legacy_tested

    if cert and probe.trusted and not issues:
        summary = f"Valid certificate, {cert.days_left} days left · {probe.protocol}"
    elif cert:
        summary = f"{len(issues)} TLS issue(s) · certificate expires in {cert.days_left} days"
    else:
        summary = f"{len(issues)} TLS issue(s)"
    return _with_issues(Outcome("ok", summary, data, issues, reachable=True))


def run_tls(url: str) -> Outcome:
    return evaluate_tls(net.probe_tls(urlsplit(url).hostname or ""))


# --- DNS ------------------------------------------------------------------------------------


class DNSUnavailable(Exception):
    pass


def _resolver() -> dns.resolver.Resolver:
    r = dns.resolver.Resolver()
    r.lifetime = 6
    return r


def _lookup(resolver: dns.resolver.Resolver, name: str, rtype: str) -> list[str] | None:
    """Records as text, [] when the name exists without that type, None when the name is absent."""
    try:
        return [
            r.to_text().strip('"')
            if rtype != "TXT"
            else b"".join(r.strings).decode("utf-8", "replace")
            for r in resolver.resolve(name, rtype)
        ]
    except dns.resolver.NXDOMAIN:
        return None
    except dns.resolver.NoAnswer:
        return []
    except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
        raise DNSUnavailable(type(exc).__name__) from exc


def collect_dns(domain: str) -> dict[str, Any]:
    r = _resolver()
    ns = _lookup(r, domain, "NS")
    if ns is None:
        return {"exists": False}
    return {
        "exists": True,
        "ns": sorted(n.rstrip(".").lower() for n in ns),
        "a": _lookup(r, domain, "A") or [],
        "aaaa": _lookup(r, domain, "AAAA") or [],
        "mx": sorted(_lookup(r, domain, "MX") or []),
        "caa": _lookup(r, domain, "CAA") or [],
    }


def evaluate_dns(records: dict[str, Any], previous_ns: list[str] | None) -> Outcome:
    if not records.get("exists"):
        return Outcome(
            "failing", "Domain does not resolve", records, [Issue("domain_not_resolving")]
        )
    issues: list[Issue] = []
    ns = records.get("ns", [])
    if previous_ns and set(previous_ns) != set(ns):
        issues.append(Issue("nameservers_changed", {"previous": previous_ns, "current": ns}))
    if len(ns) == 1:
        issues.append(Issue("single_nameserver", {"nameservers": ns}))
    if not records.get("caa"):
        issues.append(Issue("missing_caa"))
    summary = f"{len(ns)} nameserver(s), {len(records.get('a', []))} IPv4 address(es)"
    if records.get("mx"):
        summary += f", {len(records['mx'])} mail server(s)"
    return _with_issues(Outcome("ok", summary, records, issues, reachable=True))


def run_dns(domain: str, previous_ns: list[str] | None) -> Outcome:
    try:
        return evaluate_dns(collect_dns(domain), previous_ns)
    except DNSUnavailable as exc:
        return Outcome(
            "error",
            "DNS servers did not answer. We'll try again on the next run.",
            {"error": str(exc)},
        )


# --- Email security -------------------------------------------------------------------------


def evaluate_email(spf: list[str], dmarc: list[str], has_mx: bool) -> Outcome:
    issues: list[Issue] = []
    data: dict[str, Any] = {"spf": spf[:3], "dmarc": dmarc[:3], "has_mx": has_mx}
    spf_records = [s for s in spf if s.lower().startswith("v=spf1")]
    if not spf_records:
        issues.append(Issue("missing_spf"))
    else:
        tokens = spf_records[0].lower().split()
        all_terms = [t for t in tokens if t.lstrip("+-~?") == "all"]
        qualifier = (all_terms[-1][0] if all_terms[-1][0] in "+-~?" else "+") if all_terms else None
        if qualifier == "+":
            issues.append(Issue("permissive_spf", {"record": spf_records[0][:300]}))
        elif qualifier in (None, "?"):
            issues.append(Issue("weak_spf", {"record": spf_records[0][:300]}))
    dmarc_records = [d for d in dmarc if d.lower().replace(" ", "").startswith("v=dmarc1")]
    if not dmarc_records:
        issues.append(Issue("missing_dmarc"))
    else:
        policy = re.search(r"\bp\s*=\s*(\w+)", dmarc_records[0], re.I)
        data["dmarc_policy"] = policy.group(1).lower() if policy else None
        if not policy or policy.group(1).lower() == "none":
            issues.append(Issue("dmarc_not_enforced", {"record": dmarc_records[0][:300]}))
    summary = "SPF and DMARC configured" if not issues else f"{len(issues)} email issue(s) found"
    return _with_issues(Outcome("ok", summary, data, issues, reachable=True))


def run_email_security(domain: str) -> Outcome:
    r = _resolver()
    try:
        txt = _lookup(r, domain, "TXT")
        if txt is None:
            # Can't judge email settings for a missing domain; the DNS check reports it.
            return Outcome("error", "Domain does not resolve (see the DNS check)", {})
        dmarc = _lookup(r, f"_dmarc.{domain}", "TXT") or []
        mx = _lookup(r, domain, "MX") or []
    except DNSUnavailable as exc:
        return Outcome(
            "error",
            "DNS servers did not answer. We'll try again on the next run.",
            {"error": str(exc)},
        )
    return evaluate_email(txt, dmarc, bool(mx))
