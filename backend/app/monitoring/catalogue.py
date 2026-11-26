"""Every condition the monitoring engine can report, written for a non-technical business owner.

Each rule belongs to one check type. When that check runs successfully and no longer sees the
condition, the matching open finding is resolved automatically, unless the rule is "sticky"
(a one-off event such as a nameserver change, which a person must review).
"""

from dataclasses import dataclass

SEVERITY_SCORE = {"critical": 95, "high": 80, "medium": 55, "low": 25, "informational": 0}
SEVERITY_ORDER = ["informational", "low", "medium", "high", "critical"]


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else 0


@dataclass(frozen=True)
class Rule:
    key: str
    check_type: str
    severity: str
    title: str
    description: str
    impact: str
    recommendation: str
    sticky: bool = False


_RULES = [
    # --- Uptime -----------------------------------------------------------------------------
    Rule(
        "website_unreachable",
        "uptime",
        "high",
        "Website is down",
        "Your website did not respond on two checks in a row.",
        "Customers cannot reach you, and an unexpected outage can be a sign of an attack or an "
        "expired hosting account.",
        "Check your hosting provider's status page and dashboard. If the site was changed "
        "recently, ask your web developer to roll back the change.",
    ),
    Rule(
        "website_server_error",
        "uptime",
        "high",
        "Website is returning server errors",
        "Your website answered, but with an error page (HTTP 5xx) on two checks in a row.",
        "Visitors see an error instead of your site. Server errors can also reveal technical "
        "details to attackers.",
        "Ask your web developer or hosting provider to check the server logs.",
    ),
    Rule(
        "website_slow",
        "uptime",
        "low",
        "Website is responding slowly",
        "Your website took more than 5 seconds to respond.",
        "Slow pages lose customers and can indicate an overloaded or misconfigured server.",
        "Ask your hosting provider or developer to review server capacity and caching.",
    ),
    # --- TLS --------------------------------------------------------------------------------
    Rule(
        "https_unavailable",
        "tls",
        "high",
        "Website does not support HTTPS",
        "We could not open a secure (HTTPS) connection to your website.",
        "Without HTTPS, passwords, payment details and form submissions can be read or changed "
        "by anyone on the same network, such as public Wi-Fi.",
        "Install a TLS certificate. Most hosting providers offer free certificates "
        "(Let's Encrypt) that renew automatically.",
    ),
    Rule(
        "tls_certificate_expired",
        "tls",
        "critical",
        "TLS certificate has expired",
        "The certificate that secures your website has expired.",
        "Browsers show a full-page security warning, so most visitors will leave. Customers "
        "may also learn to click through warnings, which helps attackers.",
        "Renew the certificate today with your hosting provider and turn on automatic renewal.",
    ),
    Rule(
        "tls_certificate_expiring_14d",
        "tls",
        "high",
        "TLS certificate expires within 14 days",
        "The certificate that secures your website expires soon.",
        "When it expires, visitors will see a security warning instead of your site.",
        "Renew the certificate now and turn on automatic renewal.",
    ),
    Rule(
        "tls_certificate_expiring_30d",
        "tls",
        "medium",
        "TLS certificate expires within 30 days",
        "The certificate that secures your website expires within a month.",
        "If it isn't renewed in time, visitors will see a security warning.",
        "Confirm automatic renewal is on, or schedule the renewal.",
    ),
    Rule(
        "tls_certificate_invalid",
        "tls",
        "high",
        "TLS certificate is not trusted",
        "Browsers do not trust your website's certificate (for example it is self-signed, "
        "issued for a different name, or missing its intermediate certificate).",
        "Visitors see a security warning, and the connection could be intercepted without "
        "anyone noticing.",
        "Install a certificate from a trusted authority that covers this exact address, "
        "including the full certificate chain.",
    ),
    Rule(
        "tls_legacy_protocol",
        "tls",
        "medium",
        "Outdated TLS versions are enabled",
        "Your server still accepts TLS 1.0 or 1.1, which have known weaknesses.",
        "Attackers can force a weaker connection, and payment-card standards no longer allow "
        "these versions.",
        "Ask your hosting provider to allow only TLS 1.2 and TLS 1.3.",
    ),
    # --- Security headers -------------------------------------------------------------------
    Rule(
        "http_not_redirected",
        "security_headers",
        "medium",
        "Plain HTTP is not redirected to HTTPS",
        "Visiting the http:// address of your site does not send people to the secure "
        "https:// version.",
        "Visitors who type your address can end up on an unencrypted page where logins and "
        "forms can be intercepted.",
        "Configure a permanent (301) redirect from http:// to https:// for every page.",
    ),
    Rule(
        "missing_hsts",
        "security_headers",
        "medium",
        "HSTS is not enabled",
        "Your site does not send the Strict-Transport-Security header.",
        "Without it, browsers may still try insecure connections first, which attackers on "
        "the same network can hijack.",
        "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' once HTTPS works "
        "on all subdomains.",
    ),
    Rule(
        "weak_hsts",
        "security_headers",
        "low",
        "HSTS lifetime is too short",
        "Your Strict-Transport-Security header lasts less than 6 months.",
        "Protection lapses for returning visitors between visits.",
        "Set max-age to at least 15552000 (6 months); one year is recommended.",
    ),
    Rule(
        "missing_csp",
        "security_headers",
        "low",
        "No Content Security Policy",
        "Your site does not send a Content-Security-Policy header.",
        "If an attacker injects a script into a page, nothing tells the browser to block it. "
        "This is a common way card details are stolen from online shops.",
        "Ask your developer to add a Content-Security-Policy, starting in report-only mode.",
    ),
    Rule(
        "missing_nosniff",
        "security_headers",
        "low",
        "X-Content-Type-Options is missing",
        "Your site does not send 'X-Content-Type-Options: nosniff'.",
        "Browsers may treat uploaded files as code, which can be abused to run malicious scripts.",
        "Add the header 'X-Content-Type-Options: nosniff'.",
    ),
    Rule(
        "missing_clickjacking_protection",
        "security_headers",
        "low",
        "Site can be embedded in other websites",
        "Your site sends neither X-Frame-Options nor a CSP frame-ancestors rule.",
        "Attackers can show your pages inside their own site to trick people into clicking "
        "buttons (clickjacking).",
        "Add 'X-Frame-Options: DENY' or a CSP 'frame-ancestors' rule.",
    ),
    Rule(
        "missing_referrer_policy",
        "security_headers",
        "informational",
        "No Referrer-Policy",
        "Your site does not send a Referrer-Policy header.",
        "Full page addresses, which can include private details, may be shared with other "
        "websites.",
        "Add 'Referrer-Policy: strict-origin-when-cross-origin'.",
    ),
    Rule(
        "server_version_disclosed",
        "security_headers",
        "low",
        "Server software version is revealed",
        "Your site announces the exact version of its web server software.",
        "Attackers use version numbers to look up known vulnerabilities to try against you.",
        "Configure the web server to hide its version number.",
    ),
    Rule(
        "technology_disclosed",
        "security_headers",
        "low",
        "Technology details are revealed",
        "Your site sends an X-Powered-By header that names the software behind it.",
        "This helps attackers pick which attacks to try.",
        "Remove the X-Powered-By header in your server or application settings.",
    ),
    Rule(
        "insecure_cookies",
        "security_headers",
        "low",
        "Cookies are missing security flags",
        "Some cookies are set without the Secure or HttpOnly flag.",
        "Session cookies without these flags are easier to steal, which can let attackers take "
        "over logged-in accounts.",
        "Set Secure and HttpOnly (and SameSite) on all session cookies.",
    ),
    # --- DNS --------------------------------------------------------------------------------
    Rule(
        "domain_not_resolving",
        "dns",
        "high",
        "Domain does not resolve",
        "The domain name has no working DNS records.",
        "Your website and possibly email will not work. An unexpected change can also mean "
        "the domain has expired or been hijacked.",
        "Check the domain's registration status and DNS settings with your registrar.",
    ),
    Rule(
        "nameservers_changed",
        "dns",
        "medium",
        "Nameservers changed",
        "The nameservers for this domain are different from the last check.",
        "If nobody in your business made this change, someone may have taken control of your "
        "domain and could redirect your website and email.",
        "Confirm with whoever manages your domain that this change was planned. If not, "
        "contact your registrar immediately and change the account password.",
        sticky=True,
    ),
    Rule(
        "single_nameserver",
        "dns",
        "low",
        "Only one nameserver",
        "The domain relies on a single nameserver.",
        "If that server fails, your website and email become unreachable.",
        "Use at least two nameservers, ideally on different networks.",
    ),
    Rule(
        "missing_caa",
        "dns",
        "informational",
        "No CAA record",
        "The domain doesn't say which certificate authorities may issue certificates for it.",
        "Any authority could issue a certificate for your domain if tricked into it.",
        "Add a CAA record naming your certificate provider, e.g. 'letsencrypt.org'.",
    ),
    # --- Email security ---------------------------------------------------------------------
    Rule(
        "missing_spf",
        "email_security",
        "medium",
        "No SPF record",
        "The domain does not publish an SPF record listing who may send email for it.",
        "Scammers can more easily send emails that appear to come from your business, a "
        "common way to trick customers into paying fake invoices or MoMo requests.",
        "Publish an SPF TXT record listing your email provider, ending in '-all' or '~all'.",
    ),
    Rule(
        "permissive_spf",
        "email_security",
        "high",
        "SPF allows anyone to send",
        "The domain's SPF record ends in '+all', which authorises every server in the world.",
        "Anyone can send email that passes checks as your business.",
        "Change the end of the SPF record to '-all' (or '~all' while testing).",
    ),
    Rule(
        "weak_spf",
        "email_security",
        "low",
        "SPF does not reject unknown senders",
        "The domain's SPF record ends in '?all' or has no 'all' rule.",
        "Receiving mail servers are not told to reject forged email.",
        "End the SPF record with '-all' or '~all'.",
    ),
    Rule(
        "missing_dmarc",
        "email_security",
        "medium",
        "No DMARC policy",
        "The domain has no DMARC record.",
        "Without DMARC, receiving mail servers have no instructions for forged email using "
        "your domain, and you get no reports about spoofing attempts.",
        "Publish a TXT record at _dmarc.<your domain>, starting with 'v=DMARC1; p=none; "
        "rua=mailto:…' and moving to p=quarantine or p=reject.",
    ),
    Rule(
        "dmarc_not_enforced",
        "email_security",
        "low",
        "DMARC is monitoring only",
        "The DMARC policy is 'p=none', so forged email is reported but still delivered.",
        "Spoofed emails from your domain can still reach inboxes.",
        "After reviewing DMARC reports, move to p=quarantine and then p=reject.",
    ),
    # --- Agent connectivity -------------------------------------------------------------------
    Rule(
        "agent_offline",
        "agent_heartbeat",
        "medium",
        "Device has stopped reporting",
        "The monitoring agent on this device hasn't checked in for over 15 minutes.",
        "While a device is silent we can't see threats on it. Agents also go quiet when "
        "malware or a user switches them off.",
        "Check the device is switched on and connected. If it is, restart the monitoring agent "
        "or reinstall it.",
    ),
    # --- Endpoint health (from agent inventory) -------------------------------------------
    Rule(
        "antivirus_disabled",
        "endpoint_health",
        "high",
        "Antivirus protection is off",
        "Real-time antivirus protection is switched off on this device.",
        "Malware can run without being blocked. Attackers often switch protection off first.",
        "Turn real-time protection back on (on Windows: Windows Security → Virus & threat "
        "protection) and find out who or what switched it off.",
    ),
    Rule(
        "firewall_disabled",
        "endpoint_health",
        "medium",
        "Firewall is off",
        "The device's built-in firewall is switched off.",
        "Other devices on the network, including infected ones, can connect to services on "
        "this computer.",
        "Switch the firewall on in the operating system's security settings.",
    ),
    Rule(
        "disk_not_encrypted",
        "endpoint_health",
        "medium",
        "Disk is not encrypted",
        "The device's main disk is not encrypted (BitLocker on Windows, FileVault on macOS).",
        "If the device is lost or stolen, anyone can read the files on it, including customer "
        "and staff personal data protected under the Data Protection Act.",
        "Turn on BitLocker or FileVault and store the recovery key somewhere safe.",
    ),
    Rule(
        "security_updates_pending",
        "endpoint_health",
        "medium",
        "Security updates are waiting",
        "The operating system has security updates that haven't been installed.",
        "Unpatched systems are the most common way attackers get in.",
        "Install updates now and turn on automatic updates.",
    ),
    Rule(
        "os_unsupported",
        "endpoint_health",
        "high",
        "Operating system is no longer supported",
        "This device runs an operating system version that no longer receives security fixes.",
        "New vulnerabilities will never be fixed on this device.",
        "Upgrade to a supported version, or replace the device if it can't be upgraded.",
    ),
    Rule(
        "disk_space_low",
        "endpoint_health",
        "medium",
        "Disk is almost full",
        "Less than 10% of the main disk is free.",
        "Updates, backups and security logging can fail when a disk fills up.",
        "Free up space or add storage.",
    ),
    Rule(
        "reboot_required",
        "endpoint_health",
        "low",
        "Restart needed to finish updates",
        "Updates have been installed but won't take effect until the device restarts.",
        "Until it restarts, the device is still running the vulnerable versions.",
        "Restart the device at a convenient time.",
    ),
    # --- Detections (from security events) -------------------------------------------------
    Rule(
        "repeated_failed_logins",
        "detection",
        "high",
        "Repeated failed sign-ins",
        "There were many failed sign-in attempts on this device in a short time.",
        "This often means someone is guessing passwords. A single failed sign-in is normal; "
        "a burst like this is not.",
        "Check whether the attempts came from a known person. Make sure the targeted accounts "
        "have strong passwords, and block the source address if it's external.",
        sticky=True,
    ),
    Rule(
        "login_after_failed_attempts",
        "detection",
        "critical",
        "Successful sign-in after repeated failures",
        "An account signed in successfully right after many failed attempts.",
        "This is a strong sign that a password was guessed and an attacker is now inside.",
        "Treat this as an incident: confirm with the account owner, reset the password, sign "
        "the account out everywhere and review what it did after signing in.",
        sticky=True,
    ),
    Rule(
        "malware_detected",
        "detection",
        "critical",
        "Malware detected",
        "Security software on this device detected malicious software.",
        "Malware can steal data, encrypt files for ransom or spread to other devices.",
        "Disconnect the device from the network, run a full scan, and confirm the threat was "
        "removed before reconnecting. Change passwords used on this device.",
        sticky=True,
    ),
    Rule(
        "protection_tampering",
        "detection",
        "high",
        "Security protection was switched off",
        "Antivirus or another security control was disabled on this device.",
        "Attackers disable protection before running malware.",
        "Find out who made the change. Re-enable protection and scan the device.",
        sticky=True,
    ),
    Rule(
        "privileged_account_created",
        "detection",
        "high",
        "New administrator account",
        "An account was created or given administrator rights on this device.",
        "Attackers create admin accounts to keep access after they break in.",
        "Confirm the change was planned. If not, remove the account and investigate.",
        sticky=True,
    ),
    Rule(
        "security_log_cleared",
        "detection",
        "high",
        "Security log was cleared",
        "The device's security log was erased.",
        "Clearing logs is a common way to hide an attack.",
        "Find out who cleared the log and why. Treat it as suspicious until explained.",
        sticky=True,
    ),
    Rule(
        "suspicious_process",
        "detection",
        "high",
        "Suspicious program activity",
        "Security monitoring flagged a program behaving like known attack tools.",
        "This can be the first sign of malware or an intruder at work.",
        "Review the process details in the evidence and isolate the device if you don't "
        "recognise it.",
        sticky=True,
    ),
    Rule(
        "removable_media_used",
        "detection",
        "low",
        "Removable storage connected",
        "A USB drive or other removable storage was connected to this device.",
        "Removable drives can bring in malware or carry confidential data out.",
        "Confirm the drive is approved. Consider restricting USB storage on sensitive devices.",
        sticky=True,
    ),
    Rule(
        "high_severity_endpoint_alert",
        "detection",
        "high",
        "High-severity endpoint alert",
        "The endpoint security engine raised a high-severity alert on this device.",
        "High-severity engine alerts usually need a person to look at them.",
        "Review the alert details in the evidence and investigate the device.",
        sticky=True,
    ),
]

RULES: dict[str, Rule] = {r.key: r for r in _RULES}


def rules_for(check_type: str) -> set[str]:
    return {r.key for r in _RULES if r.check_type == check_type}
