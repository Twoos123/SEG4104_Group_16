"""Project plan data shared by the CPM calculation, the Monte Carlo simulation and the report.

Durations are in weeks as (optimistic, most likely, pessimistic). Costs are in $ thousands (CAD).
"""

# id: (name, predecessors, (a, m, b), labour_cost, non_labour_cost)
ACTIVITIES = {
    "A": ("Requirements & scope sign-off", [], (1, 2, 3), 14, 0),
    "B": ("Privacy impact assessment", ["A"], (1, 2, 3), 10, 10),
    "C": ("Architecture & data model", ["A"], (2, 3, 4), 20, 0),
    "D": ("Historical data ETL & model evaluation", ["C"], (2, 3, 4), 22, 0),
    "E": ("LLM classification service", ["B", "D"], (4, 5, 7), 56, 0),
    "F": ("Intake API & agent console", ["C"], (4, 5, 6), 46, 0),
    "G": ("GIS geocoding & duplicate detection", ["C"], (2, 3, 4), 22, 0),
    "H": ("WMS integration connector", ["C"], (5, 7, 10), 52, 0),
    "I": ("Notifications & dashboard", ["F"], (1, 2, 3), 20, 0),
    "J": ("Integration & system testing", ["E", "G", "H", "I"], (2, 3, 4), 28, 0),
    "K": ("UAT & security test", ["J"], (3, 4, 5), 18, 20),
    "L": ("Pilot deployment (roads & waste)", ["K"], (1, 2, 3), 16, 0),
    "M": ("Pilot operation & evaluation", ["L"], (2, 2, 3), 12, 0),
    "N": ("Training & change management", ["K"], (2, 3, 4), 4, 20),
    "O": ("City-wide rollout", ["M", "N"], (1, 1, 2), 8, 0),
    "P": ("Handover & lessons learned", ["O"], (1, 1, 2), 2, 0),
}

CLOUD_BUILD = 18  # hosting + LLM API during build, spread evenly over weeks 6-26
CLOUD_OPERATIONS = 22  # six months of post-launch hosting + LLM API, committed at go-live
CONTINGENCY_RESERVE = 40
MANAGEMENT_RESERVE = 20
COMMITTED_WEEKS = 26
TOLERATED_WEEKS = 30

# id: (category, risk, probability, cost impact $k, impact score 1-5, activity delayed, (min, max) weeks,
#      response strategy, response, owner)
RISKS = {
    "T1": (
        "Technical",
        "Legacy WMS API is poorly documented or access is slow, delaying integration",
        0.50,
        25,
        4,
        "H",
        (1, 3),
        "Mitigate",
        "API spike in week 3; build against a mock WMS; vendor support clause in contract",
        "Tech Lead",
    ),
    "T2": (
        "Technical",
        "Urgent safety request is classified as routine",
        0.15,
        25,
        5,
        None,
        None,
        "Mitigate",
        "Safety keywords bypass the model; confidence threshold; weekly accuracy audit",
        "QA Lead",
    ),
    "T3": (
        "Technical",
        "Classifier accuracy on real city data falls below the 92% target",
        0.30,
        20,
        4,
        "E",
        (1, 2),
        "Mitigate",
        "Evaluate on 2 years of history by week 10; agent corrections feed retraining",
        "Tech Lead",
    ),
    "T4": (
        "Technical",
        "Personal information reaches the external LLM provider",
        0.05,
        60,
        5,
        None,
        None,
        "Avoid",
        "Redact before any model call; Canadian region; no-training clause; security test",
        "Tech Lead",
    ),
    "T5": (
        "Technical",
        "System cannot handle storm-peak volume (5,000 requests/day)",
        0.15,
        10,
        3,
        "J",
        (0.5, 1),
        "Mitigate",
        "Load test at 2x peak in system testing; queue requests; autoscale containers",
        "Tech Lead",
    ),
    "E1": (
        "External",
        "LLM provider raises prices or changes its API",
        0.20,
        10,
        2,
        None,
        None,
        "Accept",
        "Monthly usage cap and alerts; provider-agnostic classifier interface; local fallback model",
        "PM",
    ),
    "E2": (
        "External",
        "Privacy review requires a design change",
        0.15,
        15,
        3,
        "B",
        (1, 2),
        "Mitigate",
        "Start the privacy impact assessment in week 2; involve the privacy office in design",
        "BA",
    ),
    "E3": (
        "External",
        "WMS vendor support is unavailable when needed",
        0.20,
        8,
        3,
        None,
        None,
        "Transfer",
        "Support hours and response times written into the vendor contract",
        "PM",
    ),
    "O1": (
        "Organizational",
        "Call-centre agents resist the new process or fear job loss",
        0.30,
        8,
        3,
        "N",
        (0.5, 1.5),
        "Mitigate",
        "Agents take part in design and UAT; reassign them to complex cases; hands-on training",
        "PM",
    ),
    "O2": (
        "Organizational",
        "A key team member leaves mid-project",
        0.10,
        15,
        3,
        None,
        None,
        "Mitigate",
        "Pair on critical modules; documentation in the repo; cross-training",
        "PM",
    ),
    "P1": (
        "Project management",
        "Scope creep: more categories or channels (for example voice) are added",
        0.25,
        12,
        3,
        None,
        None,
        "Avoid",
        "Signed scope statement; change requests go to the sponsor with cost and schedule impact",
        "PM",
    ),
    "P2": (
        "Project management",
        "Poor historical data quality delays model training",
        0.20,
        6,
        2,
        "D",
        (0.5, 1.5),
        "Mitigate",
        "Profile the legacy export in week 3; ETL rejects are logged and reviewed",
        "BA",
    ),
}


def probability_score(p: float) -> int:
    """Map a probability to the 1-5 scale used on the severity matrix."""
    for limit, score in ((0.10, 1), (0.20, 2), (0.35, 3), (0.50, 4)):
        if p <= limit:
            return score
    return 5
