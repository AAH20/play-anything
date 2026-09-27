"""Selectable capability plans and explicit USD/month scenario accounting."""
from play_anything.core.hosting_costs import estimate_hosting
from decimal import Decimal, InvalidOperation, ROUND_CEILING


# Illustrative planning allowances, not provider prices or implementation quotes.
# id, title, category, dependencies, setup hours, monthly fixed, variable/active.
_ROWS = [
    ("pitch", "Investor pitch & presentation studio", "Business", [], 4, 0, 0),
    ("world", "World runtime", "Foundation", [], 8, 5, .01),
    ("repository", "Repository intelligence", "Foundation", ["world"], 12, 3, .02),
    ("skills", "Skill progression", "Gameplay", ["world"], 10, 0, .01),
    ("maps", "Maps & dungeons", "Gameplay", ["world"], 16, 2, .02),
    ("quests", "Quest design", "Gameplay", ["skills", "maps"], 12, 0, .01),
    ("npcs", "NPC mentors", "Gameplay", ["maps"], 8, 0, .01),
    ("context", "Context selection", "Intelligence", ["repository"], 8, 2, .01),
    ("agent", "Agent & harness bridge", "Intelligence", ["context"], 10, 2, .02),
    ("voice", "Voice interaction", "Intelligence", ["npcs"], 12, 3, .05),
    ("sandbox", "Task scheduling", "Operations", ["world"], 12, 5, .03),
    ("economy", "Rewards & economy", "Gameplay", ["world"], 10, 0, .01),
    ("drift", "Repository change tracking", "Operations", ["repository", "quests"], 8, 2, .01),
    ("fairplay", "Submission checks", "Operations", ["sandbox", "quests"], 12, 2, .02),
    ("studio", "Custom games & maps", "Creator tools", ["maps", "quests"], 20, 5, .03),
    ("personalization", "Personalized learning", "Creator tools", ["skills"], 12, 2, .01),
    ("arena", "Model evaluation arena", "Creator tools", ["studio", "fairplay"], 16, 5, .04),
    ("enterprise", "Enterprise infrastructure model", "Operations", ["sandbox"], 24, 10, .05),
    ("consortium", "Custom enterprise engagements", "Business", ["enterprise"], 12, 0, 0),
    ("analytics", "Activation & business metrics", "Business", ["world"], 12, 2, .01),
]

CATALOG = [dict(id=r[0], title=r[1], category=r[2], requires=r[3], hours=r[4],
                fixed=r[5], variable=r[6]) for r in _ROWS]
DEFAULTS = dict(active=1000, paying=100, price=15, hourly=50, maintenance=8,
                overhead=50, acquisition=100, new_customers=10, platform_pct=10,
                payment_pct=3, transaction_fee=.30, refund_pct=2,
                input_tokens=5000, output_tokens=1000, input_rate=1, output_rate=4)


def resolve_modules(selected):
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        raise ValueError("Select modules by their IDs.")
    lookup = {m["id"]: m for m in CATALOG}
    if any(x not in lookup for x in selected):
        raise ValueError("Unknown module selected.")
    included = {"world"}
    def include(key):
        included.add(key)
        for dependency in lookup[key]["requires"]:
            if dependency not in included:
                include(dependency)
    for key in selected:
        include(key)
    return [m["id"] for m in CATALOG if m["id"] in included]


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{name} must be a nonnegative number.")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} must be a number.") from None
    if not number.is_finite() or number < 0 or number > Decimal('1000000000'):
        raise ValueError(f"{name} must be between 0 and 1 billion.")
    return number


def calculate_plan(selected, assumptions=None, overrides=None, hosting=None):
    """Calculate cash contribution and operating result, before tax/amortization.

    One paying customer is one monthly transaction. Variable module and AI costs
    apply to all active users. Break-even holds the paid/active ratio constant.
    """
    if assumptions is not None and not isinstance(assumptions, dict):
        raise ValueError("Assumptions must be an object.")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("Module costs must be an object.")
    raw = {**DEFAULTS, **(assumptions or {})}
    if set(raw) != set(DEFAULTS):
        raise ValueError("Unknown accounting assumption.")
    a = {k: _number(v, k) for k, v in raw.items()}
    for key in ("active", "paying", "new_customers"):
        if a[key] != a[key].to_integral_value():
            raise ValueError(f"{key} must be a whole number.")
    if a["paying"] > a["active"]:
        raise ValueError("Paying customers cannot exceed active users.")
    if a["new_customers"] > a["paying"]:
        raise ValueError("New customers cannot exceed paying customers.")
    if any(a[k] > 100 for k in ("platform_pct", "payment_pct", "refund_pct")):
        raise ValueError("Percentages must be between 0 and 100.")
    modules = resolve_modules(selected)
    rows = []
    for module in CATALOG:
        if module["id"] not in modules:
            continue
        override = (overrides or {}).get(module["id"], {})
        if not isinstance(override, dict) or set(override) - {"hours", "fixed", "variable"}:
            raise ValueError("Unknown module cost field.")
        values = {key: _number(override.get(key, module[key]), key)
                  for key in ("hours", "fixed", "variable")}
        rows.append(dict(id=module["id"], title=module["title"], **values,
                         setup=values["hours"] * a["hourly"],
                         monthly=values["fixed"] + values["variable"] * a["active"]))
    if set(overrides or {}) - {m["id"] for m in CATALOG}:
        raise ValueError("Unknown module cost override.")
    ai_per_active = ((a["input_tokens"] * a["input_rate"] +
                      a["output_tokens"] * a["output_rate"]) / 1000000
                     if "agent" in modules else Decimal(0))
    gross = a["paying"] * a["price"]
    refunds = gross * a["refund_pct"] / 100
    fees = gross * (a["platform_pct"] + a["payment_pct"]) / 100 + a["paying"] * a["transaction_fee"]
    variable = sum((r["variable"] for r in rows), Decimal(0)) * a["active"]
    ai = ai_per_active * a["active"]
    hosting_plan = estimate_hosting(hosting)
    fixed = Decimal(str(hosting_plan["monthly"])) + sum((r["fixed"] for r in rows), Decimal(0)) + a["maintenance"] * a["hourly"] + a["overhead"]
    contribution = gross - refunds - fees - variable - ai
    profit = contribution - fixed - a["acquisition"]
    per_payer = contribution / a["paying"] if a["paying"] else None
    setup = sum((r["setup"] for r in rows), Decimal(0))
    results = dict(gross=gross, refunds=refunds, fees=fees, module_variable=variable,
                   ai=ai, fixed=fixed, contribution=contribution, profit=profit,
                   setup=setup, total_monthly=refunds + fees + variable + ai + fixed + a["acquisition"],
                   contribution_per_payer=per_payer,
                   margin_pct=contribution / gross * 100 if gross else None,
                   cac=a["acquisition"] / a["new_customers"] if a["new_customers"] else None,
                   break_even_payers=int(((fixed + a["acquisition"]) / per_payer).to_integral_value(rounding=ROUND_CEILING))
                       if per_payer is not None and per_payer > 0 else None,
                   setup_payback_months=setup / profit if profit > 0 else None)
    def output(value):
        if isinstance(value, Decimal):
            return float(value.quantize(Decimal('.000001')))
        return value
    return dict(hosting=hosting_plan, modules=modules, assumptions={k: output(v) for k, v in a.items()},
                rows=[{k: output(v) for k, v in row.items()} for row in rows],
                **{k: output(v) for k, v in results.items()})
