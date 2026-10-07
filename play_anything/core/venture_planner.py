"""Selectable capability plans and explicit USD/month scenario accounting."""
import math
import sys
from decimal import (
    Context, Decimal, DecimalException, DivisionByZero, InvalidOperation, Overflow,
    ROUND_CEILING, ROUND_HALF_EVEN, Underflow, localcontext,
)
from play_anything.core.hosting_costs import estimate_hosting


_MAX_FLOAT_DECIMAL = Decimal.from_float(sys.float_info.max)
_JSON_INTEGER_DIGIT_LIMIT = 4300
# Computation bounds make results stable across caller Decimal contexts.
_CALCULATION_PRECISION = 50
_CALCULATION_EMIN = -999999
_CALCULATION_EMAX = 999999


def _calculation_context():
    context = Context(
        prec=_CALCULATION_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=_CALCULATION_EMIN,
        Emax=_CALCULATION_EMAX,
        capitals=1,
        clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (DivisionByZero, InvalidOperation, Overflow, Underflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _output_integer_digit_limit():
    get_limit = getattr(sys, "get_int_max_str_digits", None)
    runtime_limit = get_limit() if get_limit is not None else 0
    if runtime_limit == 0:
        return _JSON_INTEGER_DIGIT_LIMIT
    return min(runtime_limit, _JSON_INTEGER_DIGIT_LIMIT)


def _finite_ratio(numerator, denominator, name):
    """Calculate a ratio only when it can be returned as a finite JSON number."""
    if numerator == 0:
        return Decimal(0)
    exponent_gap = abs(numerator).adjusted() - abs(denominator).adjusted()
    if exponent_gap > 310:
        raise ValueError(f"{name} exceeds the finite numeric output range.")
    precision = max(28, exponent_gap + 8)
    try:
        with localcontext() as context:
            context.prec = precision
            result = numerator / denominator
    except DecimalException as exc:
        raise ValueError(f"{name} exceeds the finite numeric output range.") from exc
    if not result.is_finite() or abs(result) > _MAX_FLOAT_DECIMAL:
        raise ValueError(f"{name} exceeds the finite numeric output range.")
    return result


def _break_even_payers(fixed_cost, contribution_per_payer):
    if contribution_per_payer is None or contribution_per_payer <= 0:
        return None
    required = max(Decimal(0), fixed_cost)
    if required == 0:
        return 0

    digit_limit = _output_integer_digit_limit()
    try:
        with localcontext() as context:
            context.prec = max(28, digit_limit + 8)
            digit_threshold = contribution_per_payer.scaleb(digit_limit)
            if required >= digit_threshold:
                raise ValueError(
                    "break_even_payers exceeds the JSON integer digit limit "
                    f"({digit_limit})."
                )
            estimate = (required / contribution_per_payer).to_integral_value(
                rounding=ROUND_CEILING
            )
    except DecimalException as exc:
        raise ValueError(
            "break_even_payers exceeds the supported numeric range."
        ) from exc
    if estimate and estimate.adjusted() + 1 > digit_limit:
        raise ValueError(
            "break_even_payers exceeds the JSON integer digit limit "
            f"({digit_limit})."
        )
    return int(estimate)


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
    """Calculate a plan in a stable Decimal context independent of callers."""
    with localcontext(_calculation_context()) as context:
        try:
            return _calculate_plan(selected, assumptions, overrides, hosting)
        except DecimalException as exc:
            if context.flags[Underflow]:
                raise ValueError("Estimate underflowed the supported Decimal range.") from exc
            raise ValueError("Estimate exceeded the supported Decimal range.") from exc


def _calculate_plan(selected, assumptions=None, overrides=None, hosting=None):
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
    if a["paying"] > 0 and a["price"] > 0 and gross == 0:
        raise ValueError("gross underflowed the supported Decimal range.")
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
    margin = _finite_ratio(contribution * 100, gross, "margin_pct") if gross else None
    payback = _finite_ratio(setup, profit, "setup_payback_months") if profit > 0 else None
    break_even = _break_even_payers(fixed + a["acquisition"], per_payer)
    results = dict(gross=gross, refunds=refunds, fees=fees, module_variable=variable,
                   ai=ai, fixed=fixed, contribution=contribution, profit=profit,
                   setup=setup, total_monthly=refunds + fees + variable + ai + fixed + a["acquisition"],
                   contribution_per_payer=per_payer,
                   margin_pct=margin,
                   cac=a["acquisition"] / a["new_customers"] if a["new_customers"] else None,
                   break_even_payers=break_even,
                   setup_payback_months=payback)
    def output(value):
        if isinstance(value, Decimal):
            if not value.is_finite() or abs(value) > _MAX_FLOAT_DECIMAL:
                raise ValueError("Calculated estimate exceeds the finite numeric output range.")
            precision = max(28, value.adjusted() + 7)
            try:
                with localcontext() as context:
                    context.prec = precision
                    rounded = value.quantize(
                        Decimal('.000001'), rounding=ROUND_HALF_EVEN
                    )
            except DecimalException as exc:
                raise ValueError(
                    "Calculated estimate cannot be represented at six decimal places."
                ) from exc
            result = float(rounded)
            if not math.isfinite(result):
                raise ValueError("Calculated estimate exceeds the finite numeric output range.")
            return result
        return value
    return dict(hosting=hosting_plan, modules=modules, assumptions={k: output(v) for k, v in a.items()},
                rows=[{k: output(v) for k, v in row.items()} for row in rows],
                **{k: output(v) for k, v in results.items()})
