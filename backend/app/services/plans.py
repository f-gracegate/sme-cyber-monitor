"""Commercial plans. Prices are the proposed launch prices, pending validation with SMEs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    monthly_price_ghs: int | None
    asset_limit: int | None
    member_limit: int | None
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "starter": Plan(
        "starter",
        "Starter",
        150,
        5,
        3,
        (
            "Up to 5 monitored assets",
            "External website and domain monitoring",
            "Basic security findings",
            "Email alerts",
            "Monthly report",
        ),
    ),
    "business": Plan(
        "business",
        "Business",
        350,
        20,
        10,
        (
            "Up to 20 monitored assets",
            "Endpoint monitoring allowance",
            "Website and domain monitoring",
            "Risk and remediation management",
            "Email alerts and monthly reports",
        ),
    ),
    "professional": Plan(
        "professional",
        "Professional",
        750,
        50,
        25,
        (
            "Up to 50 monitored assets",
            "Expanded endpoint and server coverage",
            "Network collector allowance",
            "Advanced alerts and reports",
            "Priority support",
        ),
    ),
    "enterprise": Plan(
        "enterprise",
        "Enterprise",
        None,
        None,
        None,
        (
            "Custom asset limits",
            "Dedicated integrations",
            "Network monitoring deployment",
            "Custom retention and SLAs",
        ),
    ),
}


def get_plan(code: str) -> Plan:
    return PLANS.get(code, PLANS["starter"])
