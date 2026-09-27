/* Scenario allowances are editable examples, not quotes. */
const CreatorModel = (() => {
const catalog = [{"id": "pitch", "title": "Investor pitch & presentation studio", "category": "Business", "requires": [], "hours": 4, "fixed": 0, "variable": 0},
  {
    "id": "world",
    "title": "World runtime",
    "category": "Foundation",
    "requires": [],
    "hours": 8,
    "fixed": 5,
    "variable": 0.01
  },
  {
    "id": "repository",
    "title": "Repository intelligence",
    "category": "Foundation",
    "requires": [
      "world"
    ],
    "hours": 12,
    "fixed": 3,
    "variable": 0.02
  },
  {
    "id": "skills",
    "title": "Skill progression",
    "category": "Gameplay",
    "requires": [
      "world"
    ],
    "hours": 10,
    "fixed": 0,
    "variable": 0.01
  },
  {
    "id": "maps",
    "title": "Maps & dungeons",
    "category": "Gameplay",
    "requires": [
      "world"
    ],
    "hours": 16,
    "fixed": 2,
    "variable": 0.02
  },
  {
    "id": "quests",
    "title": "Quest design",
    "category": "Gameplay",
    "requires": [
      "skills",
      "maps"
    ],
    "hours": 12,
    "fixed": 0,
    "variable": 0.01
  },
  {
    "id": "npcs",
    "title": "NPC mentors",
    "category": "Gameplay",
    "requires": [
      "maps"
    ],
    "hours": 8,
    "fixed": 0,
    "variable": 0.01
  },
  {
    "id": "context",
    "title": "Context selection",
    "category": "Intelligence",
    "requires": [
      "repository"
    ],
    "hours": 8,
    "fixed": 2,
    "variable": 0.01
  },
  {
    "id": "agent",
    "title": "Agent & harness bridge",
    "category": "Intelligence",
    "requires": [
      "context"
    ],
    "hours": 10,
    "fixed": 2,
    "variable": 0.02
  },
  {
    "id": "voice",
    "title": "Voice interaction",
    "category": "Intelligence",
    "requires": [
      "npcs"
    ],
    "hours": 12,
    "fixed": 3,
    "variable": 0.05
  },
  {
    "id": "sandbox",
    "title": "Task scheduling",
    "category": "Operations",
    "requires": [
      "world"
    ],
    "hours": 12,
    "fixed": 5,
    "variable": 0.03
  },
  {
    "id": "economy",
    "title": "Rewards & economy",
    "category": "Gameplay",
    "requires": [
      "world"
    ],
    "hours": 10,
    "fixed": 0,
    "variable": 0.01
  },
  {
    "id": "drift",
    "title": "Repository change tracking",
    "category": "Operations",
    "requires": [
      "repository",
      "quests"
    ],
    "hours": 8,
    "fixed": 2,
    "variable": 0.01
  },
  {
    "id": "fairplay",
    "title": "Submission checks",
    "category": "Operations",
    "requires": [
      "sandbox",
      "quests"
    ],
    "hours": 12,
    "fixed": 2,
    "variable": 0.02
  },
  {
    "id": "studio",
    "title": "Custom games & maps",
    "category": "Creator tools",
    "requires": [
      "maps",
      "quests"
    ],
    "hours": 20,
    "fixed": 5,
    "variable": 0.03
  },
  {
    "id": "personalization",
    "title": "Personalized learning",
    "category": "Creator tools",
    "requires": [
      "skills"
    ],
    "hours": 12,
    "fixed": 2,
    "variable": 0.01
  },
  {
    "id": "arena",
    "title": "Model evaluation arena",
    "category": "Creator tools",
    "requires": [
      "studio",
      "fairplay"
    ],
    "hours": 16,
    "fixed": 5,
    "variable": 0.04
  },
  {
    "id": "enterprise",
    "title": "Enterprise infrastructure model",
    "category": "Operations",
    "requires": [
      "sandbox"
    ],
    "hours": 24,
    "fixed": 10,
    "variable": 0.05
  },
  {
    "id": "consortium",
    "title": "Custom enterprise engagements",
    "category": "Business",
    "requires": [
      "enterprise"
    ],
    "hours": 12,
    "fixed": 0,
    "variable": 0
  },
  {
    "id": "analytics",
    "title": "Activation & business metrics",
    "category": "Business",
    "requires": [
      "world"
    ],
    "hours": 12,
    "fixed": 2,
    "variable": 0.01
  }
];
const defaults = {"active": 1000, "paying": 100, "price": 15, "hourly": 50, "maintenance": 8, "overhead": 50, "acquisition": 100, "new_customers": 10, "platform_pct": 10, "payment_pct": 3, "transaction_fee": 0.3, "refund_pct": 2, "input_tokens": 5000, "output_tokens": 1000, "input_rate": 1, "output_rate": 4};
function resolve(selected) {
  const result = new Set(['world']);
  const lookup = new Map(catalog.map(m => [m.id, m]));
  function add(id) {
    if (!lookup.has(id)) throw Error('Unknown module: ' + id);
    result.add(id);
    lookup.get(id).requires.forEach(dep => { if (!result.has(dep)) add(dep); });
  }
  selected.forEach(add);
  return catalog.filter(m => result.has(m.id)).map(m => m.id);
}
function calculate(selected, assumptions = {}, overrides = {}, hostingSettings = {}) {
  const a = {...defaults, ...assumptions};
  if (Object.keys(a).some(k => !(k in defaults))) throw Error('Unknown accounting assumption.');
  Object.keys(a).forEach(k => {
    if (a[k] === '' || typeof a[k] === 'boolean' || !Number.isFinite(Number(a[k])) || Number(a[k]) < 0 || Number(a[k]) > 1e9) throw Error(k + ' must be between 0 and 1 billion.');
    a[k] = Number(a[k]);
  });
  for (const k of ['active', 'paying', 'new_customers']) if (!Number.isInteger(a[k])) throw Error(k + ' must be a whole number.');
  if (a.paying > a.active) throw Error('Paying customers cannot exceed active users.');
  if (a.new_customers > a.paying) throw Error('New customers cannot exceed paying customers.');
  if (['platform_pct','payment_pct','refund_pct'].some(k => a[k] > 100)) throw Error('Percentages must be between 0 and 100.');
  const modules = resolve(selected);
  const rows = catalog.filter(m => modules.includes(m.id)).map(m => {
    const values = {...m, ...(overrides[m.id] || {})};
    ['hours','fixed','variable'].forEach(k => {
      if (values[k] === '' || !Number.isFinite(Number(values[k])) || Number(values[k]) < 0 || Number(values[k]) > 1e9) throw Error(m.title + ': enter a nonnegative cost.');
      values[k] = Number(values[k]);
    });
    return {...values, setup: values.hours*a.hourly, monthly: values.fixed + values.variable*a.active};
  });
  const sum = key => rows.reduce((total,row) => total+row[key],0);
  const gross = a.paying*a.price, refunds = gross*a.refund_pct/100;
  const fees = gross*(a.platform_pct+a.payment_pct)/100+a.paying*a.transaction_fee;
  const module_variable = sum('variable')*a.active;
  const ai = modules.includes('agent') ? (a.input_tokens*a.input_rate+a.output_tokens*a.output_rate)/1e6*a.active : 0;
  const hosting = (typeof HostingModel !== 'undefined' ? HostingModel : require('./hosting-model.js')).estimate(hostingSettings);
  const fixed = hosting.monthly+sum('fixed')+a.maintenance*a.hourly+a.overhead;
  const contribution = gross-refunds-fees-module_variable-ai;
  const profit = contribution-fixed-a.acquisition;
  const contribution_per_payer = a.paying ? contribution/a.paying : null;
  return {hosting, modules, assumptions:a, rows, gross, refunds, fees, module_variable, ai, fixed, contribution, profit,
    setup:sum('setup'), total_monthly:refunds+fees+module_variable+ai+fixed+a.acquisition,
    contribution_per_payer, margin_pct:gross ? contribution/gross*100 : null,
    cac:a.new_customers ? a.acquisition/a.new_customers : null,
    break_even_payers: contribution_per_payer>0 ? Math.ceil((fixed+a.acquisition)/contribution_per_payer) : null,
    setup_payback_months: profit>0 ? sum('setup')/profit : null};
}
return {catalog, defaults, resolve, calculate};
})();
if (typeof module !== 'undefined') module.exports = CreatorModel;
