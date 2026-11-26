"""Pure rule tests: no network, no database."""

from datetime import UTC, datetime, timedelta

from app.monitoring import checks, net
from app.monitoring.catalogue import RULES


def resp(status=200, headers=None, ms=120, url="https://shop.example.com/"):
    return net.Response(
        url=url, status_code=status, headers=headers or [], elapsed_ms=ms, peer_ip="93.184.216.34"
    )


def ok(response):
    return net.FetchResult(ok=True, final=response, chain=[response])


def keys(outcome):
    return {i.rule_key for i in outcome.issues}


def test_every_rule_is_described_in_plain_language():
    for rule in RULES.values():
        assert rule.title and rule.description and rule.impact and rule.recommendation
        assert rule.severity in {"critical", "high", "medium", "low", "informational"}


def test_uptime_needs_two_failures_before_reporting_down():
    down = net.FetchResult(ok=False, error="Timed out")
    first = checks.evaluate_uptime(down, previous_failures=0)
    assert first.status == "failing" and first.issues == []
    second = checks.evaluate_uptime(down, previous_failures=1)
    assert keys(second) == {"website_unreachable"}


def test_uptime_server_errors_and_slowness():
    assert keys(checks.evaluate_uptime(ok(resp(503)), 1)) == {"website_server_error"}
    slow = checks.evaluate_uptime(ok(resp(200, ms=7000)), 0)
    assert slow.status == "warning" and keys(slow) == {"website_slow"}
    fine = checks.evaluate_uptime(ok(resp(200)), 0)
    assert fine.status == "ok" and fine.reachable


def test_unsafe_targets_are_errors_not_outages():
    out = checks.evaluate_uptime(net.FetchResult(ok=False, error="private", unsafe=True), 5)
    assert out.status == "error" and not out.issues


GOOD_HEADERS = [
    ("strict-transport-security", "max-age=31536000; includeSubDomains"),
    ("content-security-policy", "default-src 'self'; frame-ancestors 'none'"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("server", "nginx"),
    ("set-cookie", "session=abc; Path=/; Secure; HttpOnly; SameSite=Lax"),
]


def redirect_to_https():
    r = resp(301, [("location", "https://shop.example.com/")], url="http://shop.example.com/")
    return net.FetchResult(ok=True, final=r, chain=[r])


def test_well_configured_site_has_no_header_findings():
    out = checks.evaluate_headers(ok(resp(200, GOOD_HEADERS)), redirect_to_https())
    assert out.status == "ok", keys(out)


def test_missing_headers_are_reported():
    bare = [
        ("server", "Apache/2.4.41 (Ubuntu)"),
        ("x-powered-by", "PHP/7.4.3"),
        ("set-cookie", "PHPSESSID=1; path=/"),
    ]
    plain = resp(200, url="http://shop.example.com/")
    out = checks.evaluate_headers(
        ok(resp(200, bare)), net.FetchResult(ok=True, final=plain, chain=[plain])
    )
    assert keys(out) == {
        "http_not_redirected",
        "missing_hsts",
        "missing_csp",
        "missing_nosniff",
        "missing_clickjacking_protection",
        "missing_referrer_policy",
        "server_version_disclosed",
        "technology_disclosed",
        "insecure_cookies",
    }


def test_short_hsts_is_weak():
    headers = [h for h in GOOD_HEADERS if h[0] != "strict-transport-security"]
    headers.append(("strict-transport-security", "max-age=300"))
    assert keys(checks.evaluate_headers(ok(resp(200, headers)), None)) == {"weak_hsts"}


def cert(days_left: int, self_signed=False):
    now = datetime.now(UTC)
    return net.CertificateInfo(
        subject="shop.example.com",
        issuer="R11",
        not_before=now - timedelta(days=60),
        not_after=now + timedelta(days=days_left, hours=1),
        sans=["shop.example.com"],
        self_signed=self_signed,
    )


def test_tls_certificate_expiry_bands():
    def evaluate(days):
        return keys(
            checks.evaluate_tls(
                net.TLSProbe(
                    reachable=True, trusted=True, protocol="TLSv1.3", certificate=cert(days)
                )
            )
        )

    assert evaluate(200) == set()
    assert evaluate(25) == {"tls_certificate_expiring_30d"}
    assert evaluate(10) == {"tls_certificate_expiring_14d"}
    expired = checks.evaluate_tls(
        net.TLSProbe(
            reachable=True,
            trusted=False,
            trust_error="certificate has expired",
            certificate=cert(-3),
        )
    )
    assert keys(expired) == {"tls_certificate_expired"}


def test_untrusted_and_legacy_tls():
    probe = net.TLSProbe(
        reachable=True,
        trusted=False,
        trust_error="self-signed certificate",
        certificate=cert(300, self_signed=True),
        legacy_protocols=["TLSv1"],
        legacy_tested=True,
    )
    assert keys(checks.evaluate_tls(probe)) == {"tls_certificate_invalid", "tls_legacy_protocol"}


def test_https_unavailable_vs_unknown_error():
    refused = checks.evaluate_tls(net.TLSProbe(reachable=False, error="Connection refused"))
    assert keys(refused) == {"https_unavailable"}
    unknown = checks.evaluate_tls(net.TLSProbe(reachable=False, error="resolves to private"))
    assert unknown.status == "error"


def test_dns_rules():
    base = {
        "exists": True,
        "ns": ["ns1.host.com", "ns2.host.com"],
        "a": ["1.2.3.4"],
        "caa": ['0 issue "letsencrypt.org"'],
        "mx": [],
    }
    assert checks.evaluate_dns(base, ["ns1.host.com", "ns2.host.com"]).status == "ok"
    moved = checks.evaluate_dns(base, ["ns1.old.com", "ns2.old.com"])
    assert keys(moved) == {"nameservers_changed"}
    single = checks.evaluate_dns({**base, "ns": ["ns1.host.com"], "caa": []}, None)
    assert keys(single) == {"single_nameserver", "missing_caa"}
    gone = checks.evaluate_dns({"exists": False}, None)
    assert gone.status == "failing" and keys(gone) == {"domain_not_resolving"}


def test_email_rules():
    good = checks.evaluate_email(
        ["v=spf1 include:_spf.google.com -all"], ["v=DMARC1; p=reject; rua=mailto:d@x.com"], True
    )
    assert good.status == "ok"
    assert keys(checks.evaluate_email([], [], True)) == {"missing_spf", "missing_dmarc"}
    assert keys(checks.evaluate_email(["v=spf1 +all"], ["v=DMARC1; p=quarantine"], True)) == {
        "permissive_spf"
    }
    assert keys(checks.evaluate_email(["v=spf1 a mx ?all"], ["v=DMARC1; p=none"], True)) == {
        "weak_spf",
        "dmarc_not_enforced",
    }
    assert keys(checks.evaluate_email(["v=spf1 a mx"], ["v=DMARC1; p=reject"], True)) == {
        "weak_spf"
    }


def test_redirect_to_internal_address_is_refused(monkeypatch):
    original = net._request

    def fake(url, timeout):
        if url == "https://shop.example.com/":
            return resp(302, [("location", "http://169.254.169.254/latest/meta-data/")])
        return original(url, timeout)

    monkeypatch.setattr(net, "_request", fake)
    result = net.fetch("https://shop.example.com/")
    assert not result.ok and result.unsafe
