"""Dated list-price scenarios, not provider invoices. Standard library only."""
import math
from decimal import (
    Context, Decimal, DecimalException, DivisionByZero, InvalidOperation,
    Overflow, ROUND_HALF_EVEN, Underflow, localcontext,
)


def _calculation_context():
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (DivisionByZero, InvalidOperation, Overflow, Underflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _as_finite_float(value, name):
    result = float(value)
    if not math.isfinite(result) or (value != 0 and result == 0):
        raise ValueError(f"Hosting estimate for {name} exceeds the finite output range.")
    return result

DEFAULTS = dict(web='local', database='none', commercial=True, seats=1,
                builds=30, requests=10000, cpu_ms=5, mau=1000, db_gb=.1,
                storage_gb=.1, egress_gb=1, cached_gb=0, vercel_usage=0,
                extra=0)
SOURCES = {'Vercel Pro': 'https://vercel.com/docs/plans/pro-plan',
           'Vercel Hobby': 'https://vercel.com/docs/plans/hobby',
           'Cloudflare Pages': 'https://developers.cloudflare.com/pages/platform/limits/',
           'Cloudflare Workers': 'https://developers.cloudflare.com/workers/platform/pricing/',
           'Supabase': 'https://supabase.com/pricing'}


def estimate_hosting(settings=None):
    """Estimate hosting in a stable Decimal context independent of callers."""
    with localcontext(_calculation_context()) as context:
        try:
            return _estimate_hosting(settings)
        except DecimalException as exc:
            if context.flags[Underflow]:
                raise ValueError("Hosting estimate underflowed the supported Decimal range.") from exc
            raise ValueError("Hosting estimate exceeded the supported Decimal range.") from exc


def _estimate_hosting(settings=None):
    if settings is not None and not isinstance(settings, dict):
        raise ValueError('Hosting settings must be an object.')
    a = {**DEFAULTS, **(settings or {})}
    if set(a) != set(DEFAULTS):
        raise ValueError('Unknown hosting setting.')
    if a['web'] not in ('local', 'cloudflare_free', 'cloudflare_workers', 'vercel_hobby', 'vercel_pro') or a['database'] not in ('none', 'free', 'pro'):
        raise ValueError('Unknown hosting plan.')
    if type(a['commercial']) is not bool:
        raise ValueError('Commercial use must be true or false.')
    for k in set(a) - {'web', 'database', 'commercial'}:
        try:
            n = Decimal(str(a[k]))
        except Exception as exc:
            raise ValueError(f'Invalid hosting input: {k}') from exc
        if not n.is_finite() or n < 0 or n > 1e12:
            raise ValueError(f'Invalid hosting input: {k}')
        if k in ('seats', 'builds', 'requests', 'mau') and n != int(n):
            raise ValueError(f'{k} must be a whole number.')
        a[k] = n
    if a['seats'] < 1:
        raise ValueError('At least one deploying seat is required.')
    rows, warnings = [], []
    def add(name, amount, formula):
        rows.append(dict(name=name, amount=_as_finite_float(amount, name), formula=formula))
    def excess(key, limit, rate):
        return max(Decimal(0), a[key] - Decimal(str(limit))) * Decimal(str(rate))
    if a['web'] == 'vercel_hobby' and a['commercial']:
        warnings.append('Vercel Hobby is restricted to personal, non-commercial use. Choose Pro for this business.')
    if a['web'].startswith('cloudflare') and a['builds'] > 500:
        warnings.append('Cloudflare Pages Free exceeds 500 builds/month. Upgrade or reduce builds; extra build pricing is not estimated.')
    if a['web'] == 'vercel_pro':
        add('Vercel platform and deploying seats', a['seats'] * 20, '$20 × deploying seats; first seat included in platform fee')
        add('Vercel metered usage after credit', max(Decimal(0), a['vercel_usage'] - 20), 'max(0, entered eligible metered usage − $20 credit); excludes add-ons')
    if a['web'] == 'cloudflare_workers':
        add('Optional Workers paid base', 5, '$5/month; static Pages deployment itself needs no Worker')
        add('Optional Worker requests', excess('requests', 10000000, .0000003), 'max(0, monthly requests − 10M) × $0.30/M')
        add('Optional Worker CPU', max(Decimal(0), a['requests'] * a['cpu_ms'] - 30000000) * Decimal('.00000002'), 'max(0, requests × CPU ms − 30M ms) × $0.02/M ms')
    if a['database'] == 'free':
        for k, limit in dict(mau=50000, db_gb=.5, storage_gb=1, egress_gb=5, cached_gb=5).items():
            if a[k] > limit:
                warnings.append(f'Supabase Free exceeds {k} allowance ({limit}); upgrade required, no automatic free-tier overage price assumed.')
    if a['database'] == 'pro':
        add('Supabase Pro + one Micro project', 25, '$25 organization + $10 Micro compute − $10 compute credit')
        for key, limit, rate in [('mau',100000,.00325),('db_gb',8,.125),('storage_gb',100,.0213),('egress_gb',250,.09),('cached_gb',250,.03)]:
            add('Supabase ' + key, excess(key,limit,rate), f'max(0, {key} − {limit}) × ${rate}')
    add('Other hosting and add-ons allowance', a['extra'], 'Editable allowance: domains, email, backups, extra projects, observability, taxes as applicable')
    total = round(sum(r['amount'] for r in rows), 6)
    return dict(settings={k:_as_finite_float(v, k) if isinstance(v,Decimal) else v for k,v in a.items()},
                monthly=total, rows=rows, warnings=warnings, eligible=not warnings,
                estimate_type='illustrative', price_verified=False, verified_on=None,
                estimate_basis='Editable planning scenario using modeled rates; not a quote or live-verified provider price list.',
                sources=SOURCES,
                scope='Static site hosting and one Supabase project. Git clones and agent connections run locally. Free Supabase can pause after one inactive week; 2 active free projects maximum. Realtime, functions, large compute, email and other add-ons need separate allowances.')
