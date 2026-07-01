# Teilplan B: Frontend-Finanz- und Anzeige-Fixes (dashboard.js/dashboard.html) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behebt die im Pre-Release-Review bestaetigten Finanz-, Anzeige- und Dead-Code-Findings in templates/dashboard.js und templates/dashboard.html (Findings 4, 5, 6, 10, 13-Frontend, 14, 20, 21, 22, F8-Frontend-Pendant, F12-Client, 41a, 36, 39-Teil).

**Architecture:** Alle Aenderungen liegen in zwei Template-Dateien, die extract_stats.py beim Generieren in public/index.html inlined. Es gibt keinen Build-Step und keinen JS-Test-Runner; die Verifikation pro Task ist deshalb `node --check` (Syntax-Preflight) plus ein abschliessender Headless-Chromium-Smoke-Task, der das generierte Dashboard auf Konsolen-Fehler und NaN/undefined in den KPIs prueft. Kern-Designentscheidung (User-Entscheid): Die KPI "API Equivalent" nutzt in beiden Waehrungsmodi die Tages-Slice-Basis (Summe ueber F.daily_costs), dieselbe Basis wie das Tageschart.

**Tech Stack:** Vanilla JS (ES2020), Chart.js 4 via CDN, Python 3 (nur zum Regenerieren), pytest (Regressionsschutz Backend).

## Global Constraints

- Branch: `feature/dashboard-rethink-v2`. Es laufen ggf. parallele Sessions am selben Repo: vor JEDEM Commit `git status --short` pruefen und ausschliesslich die im Task genannten Dateien stagen (`git add <datei>`), niemals `git add -A`.
- KEINE Em-Dashes in neu geschriebenem Text oder Code-Kommentaren (User-Styleguide). In geloeschten/ersetzten Altzeilen duerfen sie vorkommen (exakte String-Matches).
- Kein Build-Step: templates/dashboard.js muss standalone-parsebar bleiben. Nach jeder Aenderung an dashboard.js: `node --check templates/dashboard.js` muss ohne Output durchlaufen.
- Backend-Testsuite bleibt gruen: `python3 -m pytest tests/ -q` (Stand Planerstellung: 195 passed; Teilplan A kann Tests hinzufuegen, erwartet wird "0 failed").
- `update_dashboard.sh` und Deploy-Infrastruktur niemals anfassen oder committen.
- Kontrakte aus Teilplan A (Backend), die dieser Plan KONSUMIERT, nicht definiert:
  - `D.week_anchor`: Top-Level-Feld in dashboard_data, String `"mon"`..`"sun"`, Default `"mon"` (Task 6).
  - Server-Tagesserien (`D.daily_costs`, `D.daily_tokens`, `D.daily_messages`, `D.daily_cache_efficiency`) entsprechen der Default-Ansicht: leere Sessions (messages == 0 und output_tokens == 0) ausgeschlossen, Cache-Eff-Boxplot zaehlt nur Eintraege mit messages >= 3 (Task 12).
  - Backend `total_tool_calls` = echte Tool-Aufrufe, nicht API-Calls (Task 10 ist das Frontend-Pendant).
- Reihenfolge-Abhaengigkeit: Task 6 und Task 12 erst ausfuehren, wenn Teilplan A gemerged ist (Task 6 faellt sonst auf Montag-Anker zurueck statt auf den konfigurierten Reset-Tag; Task 12 wuerde sonst Serien mit abweichender Semantik in den Fast-Path nehmen). Alle anderen Tasks sind unabhaengig von A.
- Commit-Konvention (siehe git log): `fix(dashboard): ...` fuer Verhaltensfixes, `refactor(dashboard): ...` fuer Dead-Code-Entfernung.
- Zeilennummern in diesem Plan sind Stand der Planerstellung und verschieben sich durch fruehe Tasks; die Edit-Anker sind deshalb immer die exakten Code-Strings, nicht die Nummern.

---

### Task 1: KPI "API Equivalent" auf Tages-Slice-Basis (Finding 4)

**Files:**
- Modify: `templates/dashboard.js` (filterData, ca. Zeile 661-672; renderVcKpis-Kommentar, ca. Zeile 3067-3069)

**Interfaces:**
- Consumes: `F.daily_costs` (Array von `{date, total, <modell>: cost}`), wird in filterData direkt davor gebaut bzw. aus `D.daily_costs` uebernommen.
- Produces: `F.kpi.total_cost` = Summe ueber `F.daily_costs[].total` (Tages-Slice-Basis); `F.kpi.actual_plan_cost` = `calcFilteredPlanCost` ueber die Datumsliste der Tagesserie. Konsumenten: renderKPI (Zeile 888, Legacy-Backup-UI) und renderVcKpis (Zeile 3072-3077) uebernehmen die neue Basis automatisch, weil sie `k.total_cost`/`k.actual_plan_cost` lesen.

Hintergrund: Bisher war `total_cost` die Summe voller Session-Totale aller Sessions, deren ENDE im Zeitraum liegt. Eine Session, die 2 Monate laeuft und im 7-Tage-Fenster endet, zaehlte damit komplett. Der Lokalwaehrungs-Modus summierte dagegen Tages-Slices. Nach diesem Task nutzen beide Modi, das Tageschart und die KPI dieselbe Basis.

- [ ] **Step 1: Ist-Zustand verifizieren**

Run: `grep -n "const totalCost = filteredTotalCost" templates/dashboard.js`
Expected: genau 1 Treffer (ca. Zeile 662). Bei 0 Treffern: STOPP, Plan gegen aktuellen Code abgleichen.

- [ ] **Step 2: filterData-KPI-Block umstellen**

In `templates/dashboard.js`, ersetze:

```js
  // Recalculate KPI
  const totalCost = filteredTotalCost;
```

durch:

```js
  // Recalculate KPI. total_cost uses the day-slice basis (sum over F.daily_costs):
  // multi-day sessions count only their slices inside the selected range, so this
  // KPI, the daily chart and the local-currency conversion share one attribution
  // basis. (Summing whole sessions whose end falls in range overcounted at the
  // range edge by up to the full pre-range spend of a long-running session.)
  const totalCost = F.daily_costs.reduce((s, r) => s + (r.total || 0), 0);
```

- [ ] **Step 3: actual_plan_cost auf dieselbe Datumsbasis stellen**

In `templates/dashboard.js`, ersetze (innerhalb des `F.kpi = {`-Objekts):

```js
    actual_plan_cost: calcFilteredPlanCost(dates),
```

durch:

```js
    actual_plan_cost: calcFilteredPlanCost(F.daily_costs.map(r => r.date)),
```

Hinweis: Die lokale Variable `dates` (Session-Daten) bleibt bestehen, sie wird weiter fuer `first_session`/`last_session` gebraucht. NICHT loeschen.

- [ ] **Step 4: renderVcKpis-Kommentar an die neue Realitaet anpassen**

In `templates/dashboard.js`, ersetze:

```js
  // In local-currency mode the money KPI follows the costs-tab toggle:
  // API equivalent converts per-day (matches the daily chart), paid uses the
  // actual local plan costs per period. Tokens mode keeps the USD display.
```

durch:

```js
  // Both currency modes share the day-slice basis (F.kpi.total_cost is the sum
  // of F.daily_costs): local mode converts per-day at each day's FX rate, USD
  // mode shows the same sum unconverted. Tokens mode keeps the USD display.
```

- [ ] **Step 5: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 6: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): API-equivalent KPI uses day-slice basis in both currency modes"
```

---

### Task 2: calcFilteredPlanCost liefert 0 bei leerem Filterergebnis (Finding 6)

**Files:**
- Modify: `templates/dashboard.js` (calcFilteredPlanCost, ca. Zeile 353-357)

**Interfaces:**
- Consumes: nichts Neues.
- Produces: `calcFilteredPlanCost([]) === 0` und `calcFilteredPlanCost(x)` ohne konfigurierten Plan `=== 0`. Konsumenten: filterData (Task 1) und renderVcKpis Zeile 3076.

Hintergrund: Bisher lieferte ein leeres Filterergebnis `D.kpi.actual_plan_cost` (Gesamt-Planpreis aller Zeiten). Ein 7-Tage-Filter ohne Nutzung zeigte dadurch "API Equivalent $0.00 / paid <Gesamtsumme>".

- [ ] **Step 1: Guard ersetzen**

In `templates/dashboard.js`, ersetze:

```js
function calcFilteredPlanCost(filteredDates, local) {
  if (!filteredDates.length || !D.plan) {
    const base = D.kpi.actual_plan_cost;
    return local ? base * (currentFx() || 0) : base;
  }
```

durch:

```js
function calcFilteredPlanCost(filteredDates, local) {
  // An empty range (or no configured plan) means nothing was paid in this
  // range. Falling back to the all-time plan total here made a filtered view
  // with zero usage show "API equivalent $0.00 / paid <all-time total>".
  if (!D.plan || !filteredDates.length) return 0;
```

- [ ] **Step 2: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 3: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): empty filtered range shows paid 0 instead of all-time plan cost"
```

---

### Task 3: Kumulativ-Chart konvertiert pro Tag, dann kumuliert (Finding 5)

**Files:**
- Modify: `templates/dashboard.js` (filterData ca. Zeile 555-559, renderCostCharts ca. Zeile 1158 und 1195-1202)

**Interfaces:**
- Consumes: `F.daily_costs` / `F.daily_tokens` (beide mit `.total` und `.date`), `conv(v, date)` (lokale Konvertierungsfunktion in renderCostCharts, definiert ca. Zeile 1162, bleibt unveraendert).
- Produces: `F.cumulative_costs` und `F.cumulative_tokens` existieren danach NICHT mehr (einziger Konsument war renderCostCharts; vor dem Loeschen per Grep verifizieren).

Hintergrund: Bisher wurde die kumulierte USD-Praefixsumme mit dem FX-Kurs des jeweiligen Tages multipliziert. Bei Kurswechsel zwischen Perioden reskaliert das die gesamte Vorgeschichte (Beispiel: Periode A FX 0.90 mit $100, Periode B FX 1.10 mit $100: Endpunkt 220 statt 200, Sprungstelle am Periodenwechsel).

- [ ] **Step 1: Verifizieren, dass renderCostCharts der einzige Konsument der cumulative-Serien ist**

Run: `grep -rn "cumulative_costs\|cumulative_tokens" templates/`
Expected: Treffer NUR in templates/dashboard.js (Builder in filterData, Verwendung in renderCostCharts). `cumulative_tokens_label`/`L.cumulative_tokens` sind Locale-Keys, keine Datenserien; sie bleiben. Bei Treffern in anderen Dateien: STOPP, Builder nicht loeschen, nur Schritte 3-4 ausfuehren.

- [ ] **Step 2: Tote Builder in filterData entfernen**

In `templates/dashboard.js`, ersetze:

```js
  // Recalculate cumulative costs from filtered daily costs
  let cum = 0;
  F.cumulative_costs = F.daily_costs.map(r => { cum += r.total; return {date: r.date, cost: cum}; });
  let cumTok = 0;
  F.cumulative_tokens = F.daily_tokens.map(r => { cumTok += r.total; return {date: r.date, tokens: cumTok}; });
```

durch (Leerzeile bleibt als Abschnittstrenner):

```js
  // Cumulative series are built mode-aware inside renderCostCharts()
  // (convert each day first, then accumulate).
```

- [ ] **Step 3: cumSrc-Zeile in renderCostCharts ersetzen**

In `templates/dashboard.js`, ersetze:

```js
  const cumSrc = mode === 'tokens' ? F.cumulative_tokens : F.cumulative_costs;
```

durch:

```js
  // Cumulative series: convert each day at its own FX rate first, then
  // accumulate. (Converting a running USD total with the current day's rate
  // rescaled all prior spending whenever the rate changed between periods.)
  const cumRows = mode === 'tokens' ? F.daily_tokens : F.daily_costs;
```

- [ ] **Step 4: Chart-Daten auf convert-then-cumulate umstellen**

In `templates/dashboard.js`, ersetze (im `charts.cumCost = new Chart(...)`-Block):

```js
      labels: cumSrc.map(d => d.date),
      datasets: [{ label: mode === 'tokens' ? L.cumulative_tokens_label : L.cumulative_label,
        data: cumSrc.map(d => conv(mode === 'tokens' ? d.tokens : d.cost, d.date)),
```

durch:

```js
      labels: cumRows.map(r => r.date),
      datasets: [{ label: mode === 'tokens' ? L.cumulative_tokens_label : L.cumulative_label,
        data: (() => { let acc = 0; return cumRows.map(r => { acc += conv(r.total || 0, r.date); return acc; }); })(),
```

Hinweis: `conv` ist im tokens- und usd-Modus die Identitaet, daher aendert sich dort nur die Quelle (`.total` statt `.tokens`/`.cost`), numerisch identisch zur alten Praefixsumme. Nur der local-Modus rechnet anders (korrekt).

- [ ] **Step 5: Keine Restverweise auf cumSrc**

Run: `grep -n "cumSrc" templates/dashboard.js`
Expected: 0 Treffer.

- [ ] **Step 6: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 7: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): cumulative cost chart converts per day before accumulating"
```

---

### Task 4: planMoneyValue ohne stillen USD-Fallback im Lokalmodus (Finding 22)

**Files:**
- Modify: `templates/dashboard.js` (planMoneyValue Zeile 18-29, Perioden-Tabelle ca. Zeile 2008-2010)

**Interfaces:**
- Consumes: `fmtPlanMoney(n)` (Zeile 12-17) rendert `null`/`NaN` bereits als `'–'` (En-Dash, bestehendes Verhalten). Chart-Aufrufer (Zeilen ca. 1978, 1979, 1993) behalten ihr `|| 0` und sind unveraendert null-sicher.
- Produces: `planMoneyValue(obj, base)` liefert im Lokalmodus `null`, wenn `obj[base + '_local']` fehlt (kein USD-Zahlenwert mehr als Lokalbetrag).

Hintergrund: Perioden ohne `*_local`-Preis zeigten den USD-Zahlenwert als Lokalbetrag formatiert, waehrend die Summenzeile (`total_api_cost_local`, Backend) solche Perioden auslaesst: Spalten summierten sichtbar nicht. Nach dem Fix zeigen solche Perioden `–` und die Summenzeile bleibt konsistent erklaerbar.

- [ ] **Step 1: planMoneyValue ersetzen**

In `templates/dashboard.js`, ersetze:

```js
function planMoneyValue(obj, base) {
  if (!obj) return null;
  if (base === 'plan_cost') {
    if (planCurrencyMode === 'local' && obj.plan_cost_local != null) return obj.plan_cost_local;
    return obj.plan_cost_usd;
  }
  if (planCurrencyMode === 'local') {
    const localKey = base + '_local';
    if (obj[localKey] != null) return obj[localKey];
  }
  return obj[base];
}
```

durch:

```js
function planMoneyValue(obj, base) {
  if (!obj) return null;
  // Local mode: no silent USD fallback. A period without a local price renders
  // as "-" (via fmtPlanMoney(null)) instead of a USD number posing as a local
  // amount, which made the local-mode column visibly disagree with its total.
  if (base === 'plan_cost') {
    if (planCurrencyMode === 'local') return obj.plan_cost_local != null ? obj.plan_cost_local : null;
    return obj.plan_cost_usd;
  }
  if (planCurrencyMode === 'local') {
    const localKey = base + '_local';
    return obj[localKey] != null ? obj[localKey] : null;
  }
  return obj[base];
}
```

- [ ] **Step 2: Perioden-Tabelle: `|| 0` entfernen, damit fehlende Werte als `–` rendern**

In `templates/dashboard.js`, ersetze:

```js
    const apiVal = planMoneyValue(p, 'api_cost') || 0;
    const planVal = planMoneyValue(p, 'plan_cost') || 0;
    const savingsVal = planMoneyValue(p, 'savings') || 0;
```

durch:

```js
    const apiVal = planMoneyValue(p, 'api_cost');
    const planVal = planMoneyValue(p, 'plan_cost');
    const savingsVal = planMoneyValue(p, 'savings');
```

(Die Zellen laufen durch `fmtPlanMoney(apiVal)` etc., das `null` als `–` rendert.)

- [ ] **Step 3: Verifizieren, dass kein weiterer Aufrufer nackte Arithmetik auf planMoneyValue macht**

Run: `grep -n "planMoneyValue(" templates/dashboard.js`
Expected: Treffer nur an diesen Stellen: Funktionsdefinition; `fmtPlanMoney(planMoneyValue(...))`-Aufrufe (Zeilen ca. 1891, 1948, 1949, 1950, 1954: alle null-sicher via fmtPlanMoney); Chart-Daten mit `|| 0` (ca. 1978, 1979, 1993); die drei Tabellen-Konstanten aus Step 2. Andere Muster: STOPP und pruefen.

- [ ] **Step 4: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 5: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): local-currency plan table renders missing local prices as dash instead of USD value"
```

---

### Task 5: Plan-Tabelle: Total-Zeile vom Sortieren ausnehmen (Finding 21)

**Files:**
- Modify: `templates/dashboard.js` (sortTableByColumn ca. Zeile 2698-2709, Total-Zeilen-Bau ca. Zeile 2059-2060)

**Interfaces:**
- Consumes: nichts Neues.
- Produces: generisches Opt-out `data-nosort` fuer tbody-Zeilen; gepinnte Zeilen bleiben beim Sortieren unten. Andere Tabellen sind unveraendert (kein anderes tbody setzt das Attribut).

- [ ] **Step 1: sortTableByColumn um Pinning erweitern**

In `templates/dashboard.js`, ersetze:

```js
function sortTableByColumn(table, idx, dir) {
  const tbody = table.tBodies[0];
  if (!tbody) return;
  const keyed = Array.from(tbody.rows).map(r => ({ r, k: cellSortKey(r.cells[idx]) }));
  keyed.sort((a, b) => {
    const cmp = (a.k.num && b.k.num)
      ? a.k.v - b.k.v
      : String(a.k.v).localeCompare(String(b.k.v), undefined, { numeric: true });
    return dir === 'asc' ? cmp : -cmp;
  });
  keyed.forEach(x => tbody.appendChild(x.r));
}
```

durch:

```js
function sortTableByColumn(table, idx, dir) {
  const tbody = table.tBodies[0];
  if (!tbody) return;
  const rows = Array.from(tbody.rows);
  // Rows marked data-nosort (e.g. the plan table's total row) are pinned to
  // the bottom instead of being sorted in with the data rows.
  const pinned = rows.filter(r => r.hasAttribute('data-nosort'));
  const keyed = rows.filter(r => !r.hasAttribute('data-nosort')).map(r => ({ r, k: cellSortKey(r.cells[idx]) }));
  keyed.sort((a, b) => {
    const cmp = (a.k.num && b.k.num)
      ? a.k.v - b.k.v
      : String(a.k.v).localeCompare(String(b.k.v), undefined, { numeric: true });
    return dir === 'asc' ? cmp : -cmp;
  });
  keyed.forEach(x => tbody.appendChild(x.r));
  pinned.forEach(r => tbody.appendChild(r));
}
```

- [ ] **Step 2: Total-Zeile markieren**

In `templates/dashboard.js`, ersetze:

```js
  // Total row
  const trTotal = document.createElement('tr');
  trTotal.style.fontWeight = '700';
```

durch:

```js
  // Total row
  const trTotal = document.createElement('tr');
  trTotal.setAttribute('data-nosort', '1');
  trTotal.style.fontWeight = '700';
```

- [ ] **Step 3: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 4: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): pin plan-table total row to bottom when sorting columns"
```

---

### Task 6: Wochen-Reset-Marker aus D.week_anchor (Finding 13, Frontend-Haelfte)

**Voraussetzung:** Teilplan A ist gemerged (Backend emittiert `week_anchor` top-level in dashboard_data). Ohne A faellt der Code sicher auf Montag zurueck; fuer den User (realer Reset: Dienstag) waere das bis zum A-Merge eine Verschlechterung, deshalb Reihenfolge einhalten.

**Files:**
- Modify: `templates/dashboard.js` (weekResetMarkerPlugin inkl. Kommentar, ca. Zeile 1108-1144)

**Interfaces:**
- Consumes: `D.week_anchor` (String `"mon"`..`"sun"`, optional, Default `"mon"`).
- Produces: `weekAnchorDayNum()` (Modul-Level-Helper, Rueckgabe 0-6 im JS-getDay-Schema: So=0..Sa=6). Falls spaetere Tasks/Plaene den Anker brauchen, DIESEN Helper nutzen.

- [ ] **Step 1: Kommentar und Helper ersetzen**

In `templates/dashboard.js`, ersetze:

```js
// Dashed vertical markers at each Tuesday — the weekly API-limit resets run
// Tue→Tue, so these line the daily/cumulative charts up with the billing weeks.
// Reads the chart's category x labels (YYYY-MM-DD). The line is drawn on the
// boundary *between* Monday and Tuesday so it sits at the start of the new week.
const weekResetMarkerPlugin = {
```

durch:

```js
// Dashed vertical markers at each weekly-limit reset. The anchor weekday is
// config-driven via D.week_anchor ("mon".."sun", default "mon") so the chart
// markers and the backend weekly-hit analysis share one week boundary. Reads
// the chart's category x labels (YYYY-MM-DD). The line is drawn on the
// boundary between the previous day and the anchor day, at the week start.
const _WEEK_ANCHOR_NUM = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
function weekAnchorDayNum() {
  const a = String(D.week_anchor || 'mon').slice(0, 3).toLowerCase();
  return _WEEK_ANCHOR_NUM[a] !== undefined ? _WEEK_ANCHOR_NUM[a] : 1;
}
const weekResetMarkerPlugin = {
```

- [ ] **Step 2: Anker im Draw-Loop nutzen**

In `templates/dashboard.js`, ersetze (im `afterDatasetsDraw`):

```js
    const n = labels.length;
    ctx.save();
```

durch:

```js
    const n = labels.length;
    const anchorDay = weekAnchorDayNum();
    ctx.save();
```

und ersetze:

```js
      if (dt.getDay() !== 2) continue;            // 2 = Tuesday
```

durch:

```js
      if (dt.getDay() !== anchorDay) continue;    // config-driven weekly reset anchor
```

- [ ] **Step 3: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 4: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): week reset chart markers read configurable week_anchor instead of hardcoded Tuesday"
```

---

### Task 7: Heatmap konsistent in UTC (Finding 14)

**Files:**
- Modify: `templates/dashboard.js` (renderHeatmap, ca. Zeile 1474-1528)

**Interfaces:**
- Consumes: `F.daily_messages` (UTC-Tages-Keys `YYYY-MM-DD` vom Backend), `_vcAccentRgb()`.
- Produces: keine API-Aenderung; nur interne Iteration.

Hintergrund: Die Zellen wurden mit lokalen Date-Objekten iteriert (getDay/setDate), aber per `toISOString().slice(0,10)` (UTC) gegen die UTC-Keys gelookupt. In UTC+2 verschieben sich zwischen 00:00 und 02:00 Lokalzeit alle Zellen-Keys um einen Tag (Montagszeile zeigt Sonntagsaktivitaet). Fix: komplette Iteration in UTC (die Tagesdaten SIND UTC-bucketiert, also ist das UTC-Kalendergitter die ehrliche Darstellung).

- [ ] **Step 1: renderHeatmap komplett ersetzen**

In `templates/dashboard.js`, ersetze die gesamte Funktion:

```js
function renderHeatmap() {
  const container = document.getElementById('activityHeatmap');
  const monthsEl = document.getElementById('heatmapMonths');
  if (!container) return;
  const accentRgb = _vcAccentRgb();
  const msgMap = {};
  F.daily_messages.forEach(d => { msgMap[d.date] = d.messages; });
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - (24 * 7) + 1);
  while (startDate.getDay() !== 1) startDate.setDate(startDate.getDate() - 1);
  let maxMsg = 0;
  const td = new Date(startDate);
  while (td <= today) { const k = td.toISOString().slice(0,10); maxMsg = Math.max(maxMsg, msgMap[k]||0); td.setDate(td.getDate()+1); }
  let html = '';
  const weeks = [];
  const d = new Date(startDate);
  let cw = [];
  while (d <= today) {
    const k = d.toISOString().slice(0,10);
    const m = msgMap[k]||0;
    // Variant-C heatmap: single-accent terracotta with opacity gradient
    let bg;
    if (m > 0 && maxMsg > 0) {
      const r = m / maxMsg;
      const opacity = (0.08 + r * 0.92).toFixed(3);
      bg = 'rgba(' + accentRgb + ',' + opacity + ')';
    } else {
      bg = 'color-mix(in srgb, var(--vc-fg-2) 9%, transparent)';
    }
    cw.push('<div class="heatmap-cell" style="background:'+bg+'" data-tip="'+k+': '+m+' messages" data-intensity="'+(maxMsg>0?(m/maxMsg).toFixed(2):0)+'"></div>');
    if (d.getDay()===0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); cw=[]; }
    d.setDate(d.getDate()+1);
  }
  if (cw.length>0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); }
  weeks.forEach(w => { html += '<div class="heatmap-col">'+w.join('')+'</div>'; });
  container.innerHTML = html;
  if (monthsEl) {
    const months = [];
    const md = new Date(startDate);
    let lastMonth = -1, weekIdx = 0;
    while (md <= today) {
      if (md.getDay()===1) { if(md.getMonth()!==lastMonth) { months.push({idx:weekIdx,label:md.toLocaleString('default',{month:'short'})}); lastMonth=md.getMonth(); } weekIdx++; }
      md.setDate(md.getDate()+1);
    }
    monthsEl.innerHTML = '';
    monthsEl.style.paddingLeft = '20px';
    months.forEach((m,i) => {
      const span = document.createElement('span');
      span.textContent = m.label;
      span.style.width = ((i<months.length-1 ? months[i+1].idx-m.idx : weekIdx-m.idx)*15)+'px';
      monthsEl.appendChild(span);
    });
  }
}
```

durch:

```js
function renderHeatmap() {
  const container = document.getElementById('activityHeatmap');
  const monthsEl = document.getElementById('heatmapMonths');
  if (!container) return;
  const accentRgb = _vcAccentRgb();
  const msgMap = {};
  F.daily_messages.forEach(d => { msgMap[d.date] = d.messages; });
  // Backend day keys are UTC dates. Iterate the grid in UTC as well so a
  // cell's toISOString() key always names the same calendar day as the cell's
  // grid position (local-time iteration shifted every key by one day whenever
  // the local date differed from the UTC date at render time).
  const now = new Date();
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const startDate = new Date(today);
  startDate.setUTCDate(startDate.getUTCDate() - (24 * 7) + 1);
  while (startDate.getUTCDay() !== 1) startDate.setUTCDate(startDate.getUTCDate() - 1);
  let maxMsg = 0;
  const td = new Date(startDate);
  while (td <= today) { const k = td.toISOString().slice(0,10); maxMsg = Math.max(maxMsg, msgMap[k]||0); td.setUTCDate(td.getUTCDate()+1); }
  let html = '';
  const weeks = [];
  const d = new Date(startDate);
  let cw = [];
  while (d <= today) {
    const k = d.toISOString().slice(0,10);
    const m = msgMap[k]||0;
    // Variant-C heatmap: single-accent terracotta with opacity gradient
    let bg;
    if (m > 0 && maxMsg > 0) {
      const r = m / maxMsg;
      const opacity = (0.08 + r * 0.92).toFixed(3);
      bg = 'rgba(' + accentRgb + ',' + opacity + ')';
    } else {
      bg = 'color-mix(in srgb, var(--vc-fg-2) 9%, transparent)';
    }
    cw.push('<div class="heatmap-cell" style="background:'+bg+'" data-tip="'+k+': '+m+' messages" data-intensity="'+(maxMsg>0?(m/maxMsg).toFixed(2):0)+'"></div>');
    if (d.getUTCDay()===0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); cw=[]; }
    d.setUTCDate(d.getUTCDate()+1);
  }
  if (cw.length>0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); }
  weeks.forEach(w => { html += '<div class="heatmap-col">'+w.join('')+'</div>'; });
  container.innerHTML = html;
  if (monthsEl) {
    const months = [];
    const md = new Date(startDate);
    let lastMonth = -1, weekIdx = 0;
    while (md <= today) {
      if (md.getUTCDay()===1) { if(md.getUTCMonth()!==lastMonth) { months.push({idx:weekIdx,label:md.toLocaleString('default',{month:'short',timeZone:'UTC'})}); lastMonth=md.getUTCMonth(); } weekIdx++; }
      md.setUTCDate(md.getUTCDate()+1);
    }
    monthsEl.innerHTML = '';
    monthsEl.style.paddingLeft = '20px';
    months.forEach((m,i) => {
      const span = document.createElement('span');
      span.textContent = m.label;
      span.style.width = ((i<months.length-1 ? months[i+1].idx-m.idx : weekIdx-m.idx)*15)+'px';
      monthsEl.appendChild(span);
    });
  }
}
```

- [ ] **Step 2: Verifizieren, dass keine lokalen Date-Accessoren uebrig sind**

Run: `sed -n '/^function renderHeatmap/,/^}/p' templates/dashboard.js | grep -cE "\.(getDay|setDate|getMonth)\("`
Expected: `0`

- [ ] **Step 3: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 4: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): activity heatmap iterates in UTC to match backend day keys"
```

---

### Task 8: Error-Rate-Chart folgt dem aktiven Filter (Finding 20)

**Files:**
- Modify: `templates/dashboard.js` (Instanz-Deklaration Zeile 341, renderInsights ca. Zeile 2521-2540, renderAgentsTab-Ende ca. Zeile 2669)

**Interfaces:**
- Consumes: `F.sessions` (gefilterte Sessions), `_vcLiveVar`, `_vcHexRgba` (existieren, werden in renderAgentsTab bereits genutzt).
- Produces: `errorRateChartInstance` (Modul-Level-Variable, gleiche Konvention wie `errorByCatChartInstance`).

Hintergrund: Der Chart wurde einmalig in renderInsights aus dem UNGEFILTERTEN `D.sessions` gebaut, waehrend die Nachbar-Charts derselben Errors-Subsection (errorOverview, errorByCategory, errorByTool) per applyFilter aus `F` neu gerendert werden. Der Block zieht nach renderAgentsTab um (laeuft pro Filterwechsel) und liest `F.sessions`. Nenner: echte Tool-Calls (Summe `s.tools`), konsistent zur error_rate-Semantik nach Task 10.

- [ ] **Step 1: Instanzvariable deklarieren**

In `templates/dashboard.js`, ersetze:

```js
let agentTypesChartInstance, agentDescsChartInstance, errorByCatChartInstance, errorByToolChartInstance;
```

durch:

```js
let agentTypesChartInstance, agentDescsChartInstance, errorByCatChartInstance, errorByToolChartInstance,
    errorRateChartInstance, taskDonutChartInstance;
```

(`taskDonutChartInstance` wird in Task 9 verwendet; hier mit deklariert, damit Zeile 341 nur einmal angefasst wird.)

- [ ] **Step 2: Block aus renderInsights entfernen**

In `templates/dashboard.js`, ersetze:

```js
  // Error rate over time chart
  const dailyErrors = {};
  D.sessions.forEach(s => {
    if (!dailyErrors[s.date]) dailyErrors[s.date] = {errors:0, calls:0};
    dailyErrors[s.date].errors += s.error_count || 0;
    dailyErrors[s.date].calls += s.api_calls || 0;
  });
  const errDates = Object.keys(dailyErrors).sort();
  const errRates = errDates.map(d => dailyErrors[d].calls > 0 ? +(dailyErrors[d].errors / dailyErrors[d].calls * 100).toFixed(1) : 0);
  if (errDates.length > 0) {
    const negCol = _vcLiveVar('--vc-neg', '#d24b3e');
    new Chart(document.getElementById('errorRateChart'), {
      type: 'line',
      data: {
        labels: errDates,
        datasets: [{ label: 'Error Rate (%)', data: errRates, borderColor: negCol, backgroundColor: _vcHexRgba(negCol, 0.1), fill:true, tension:0.3 }]
      },
      options: { responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a',maxTicksLimit:15}}, y:{ticks:{color:window.__vcFg3||'#918a7a'}, beginAtZero:true} } }
    });
  }
}
```

durch:

```js
}
```

(Das schliessende `}` ist das Ende von renderInsights; der Chart-Block war ihr letzter Abschnitt.)

- [ ] **Step 3: Block ans Ende von renderAgentsTab einsetzen**

In `templates/dashboard.js`, ersetze (Ende von renderAgentsTab, direkt nach dem Error-by-Tool-Chart):

```js
  // Error by tool bar chart
  const ebt = (es.by_tool || []).slice(0, 10);
  if (errorByToolChartInstance) errorByToolChartInstance.destroy();
  if (ebt.length > 0) {
    errorByToolChartInstance = new Chart(document.getElementById('errorByToolChart'), {
      type: 'bar',
      data: {
        labels: ebt.map(e => e.tool),
        datasets: [{ data: ebt.map(e => e.count), backgroundColor: _vcHexRgba(_vcLiveVar('--vc-neg', '#d24b3e'), 0.7), borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a'}}, y:{ticks:{color:window.__vcFg3||'#918a7a',font:{size:11}}} } }
    });
  }
}
```

durch:

```js
  // Error by tool bar chart
  const ebt = (es.by_tool || []).slice(0, 10);
  if (errorByToolChartInstance) errorByToolChartInstance.destroy();
  if (ebt.length > 0) {
    errorByToolChartInstance = new Chart(document.getElementById('errorByToolChart'), {
      type: 'bar',
      data: {
        labels: ebt.map(e => e.tool),
        datasets: [{ data: ebt.map(e => e.count), backgroundColor: _vcHexRgba(_vcLiveVar('--vc-neg', '#d24b3e'), 0.7), borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a'}}, y:{ticks:{color:window.__vcFg3||'#918a7a',font:{size:11}}} } }
    });
  }

  // Error rate over time. Lives here (not renderInsights) so it re-renders on
  // every filter change like the other charts in this errors subsection.
  // Denominator: real tool invocations (sum of per-tool counters), matching
  // the error_rate/total_tool_calls semantics.
  const dailyErrors = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyErrors[s.date]) dailyErrors[s.date] = {errors:0, calls:0};
    dailyErrors[s.date].errors += s.error_count || 0;
    dailyErrors[s.date].calls += Object.values(s.tools || {}).reduce((a, b) => a + (b || 0), 0);
  });
  const errDates = Object.keys(dailyErrors).sort();
  const errRates = errDates.map(d => dailyErrors[d].calls > 0 ? +(dailyErrors[d].errors / dailyErrors[d].calls * 100).toFixed(1) : 0);
  if (errorRateChartInstance) { errorRateChartInstance.destroy(); errorRateChartInstance = null; }
  if (errDates.length > 0) {
    const negCol = _vcLiveVar('--vc-neg', '#d24b3e');
    errorRateChartInstance = new Chart(document.getElementById('errorRateChart'), {
      type: 'line',
      data: {
        labels: errDates,
        datasets: [{ label: 'Error Rate (%)', data: errRates, borderColor: negCol, backgroundColor: _vcHexRgba(negCol, 0.1), fill:true, tension:0.3 }]
      },
      options: { responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a',maxTicksLimit:15}}, y:{ticks:{color:window.__vcFg3||'#918a7a'}, beginAtZero:true} } }
    });
  }
}
```

- [ ] **Step 4: Verifizieren, dass errorRateChart nur noch einmal gebaut wird**

Run: `grep -n "errorRateChart" templates/dashboard.js`
Expected: genau 2 Treffer: die Instanzvariablen-Deklaration (`errorRateChartInstance` zaehlt per Substring mit) und der `new Chart(document.getElementById('errorRateChart')...)`-Aufruf in renderAgentsTab. Kein Treffer mehr innerhalb von renderInsights.

- [ ] **Step 5: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 6: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): error-rate-over-time chart respects range/project filter"
```

---

### Task 9: taskDonut-Instanz vor Neuaufbau destroyen (Finding 39, Teil)

**Files:**
- Modify: `templates/dashboard.js` (renderAgentsTab, Task-Overview-Block ca. Zeile 2592-2616)

**Interfaces:**
- Consumes: `taskDonutChartInstance` (deklariert in Task 8, Step 1).
- Produces: keine API-Aenderung.

Hintergrund: `new Chart(document.getElementById('taskDonut'), ...)` laeuft bei jedem applyFilter auf einem frisch per innerHTML erzeugten Canvas; die alte Chart-Instanz wurde nie destroyed und akkumuliert in `Chart.instances` (Speicherleck, Theme-Toggle iteriert tote Instanzen mit).

- [ ] **Step 1: Destroy + Instanz-Zuweisung einbauen**

In `templates/dashboard.js`, ersetze:

```js
  // Task overview (range-filtered via F.insights, falls back to all-time)
  const taskEl = document.getElementById('taskOverview');
  const tasks = F.insights?.tasks || D.insights?.tasks || {};
```

durch:

```js
  // Task overview (range-filtered via F.insights, falls back to all-time)
  const taskEl = document.getElementById('taskOverview');
  const tasks = F.insights?.tasks || D.insights?.tasks || {};
  // The canvas below is recreated via innerHTML on every render; destroy the
  // previous Chart instance so it does not accumulate in Chart.instances.
  if (taskDonutChartInstance) { taskDonutChartInstance.destroy(); taskDonutChartInstance = null; }
```

und ersetze:

```js
    new Chart(document.getElementById('taskDonut'), {
      type: 'doughnut',
      data: { labels:['Completed','Pending','In Progress'], datasets:[{data:[tasks.completed,tasks.pending||0,tasks.in_progress||0], backgroundColor:[posCol, mutedCol, vcColor(0)]}] },
      options: { cutout:'70%', responsive:true, plugins:{legend:{display:false}} }
    });
```

durch:

```js
    taskDonutChartInstance = new Chart(document.getElementById('taskDonut'), {
      type: 'doughnut',
      data: { labels:['Completed','Pending','In Progress'], datasets:[{data:[tasks.completed,tasks.pending||0,tasks.in_progress||0], backgroundColor:[posCol, mutedCol, vcColor(0)]}] },
      options: { cutout:'70%', responsive:true, plugins:{legend:{display:false}} }
    });
```

- [ ] **Step 2: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 3: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): destroy stale taskDonut chart instance on re-render"
```

---

### Task 10: Gefilterte Error-Rate zaehlt echte Tool-Calls (Frontend-Pendant zu Finding 8)

**Files:**
- Modify: `templates/dashboard.js` (filterData, error_summary-Block, ca. Zeile 704)

**Interfaces:**
- Consumes: `s.tools` (Objekt `{toolName: count}` pro Session, existiert heute schon).
- Produces: `F.error_summary.total_tool_calls` und `F.error_summary.error_rate` basieren auf echten Tool-Aufrufen. Kontrakt-Partner: Backend `total_tool_calls` (Teilplan A) nutzt dieselbe Semantik; renderAgentsTab zeigt "N errors / M tool calls" damit korrekt.

Hintergrund: `api_calls` zaehlt Assistant-Responses. Eine Session mit 3 API-Calls und je 4 parallelen Tool-Uses zeigte bei 1 Fehler "1 errors / 3 tool calls" (33%) statt 1/12 (8%).

- [ ] **Step 1: fToolCalls umstellen**

In `templates/dashboard.js`, ersetze:

```js
  const fToolCalls = F.sessions.reduce((s, x) => s + (x.api_calls || 0), 0);
```

durch:

```js
  // Real tool invocations (sum of per-tool counters), matching the backend's
  // total_tool_calls semantics. api_calls counts assistant responses, which
  // undercounts parallel tool use and mislabels the "N errors / M tool calls"
  // line in the agents section.
  const fToolCalls = F.sessions.reduce((s, x) => s + Object.values(x.tools || {}).reduce((a, b) => a + (b || 0), 0), 0);
```

- [ ] **Step 2: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 3: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): filtered error rate uses real tool-call count as denominator"
```

---

### Task 11: Projekt-File-Size als Summe statt Math.max (Finding 10)

**Files:**
- Modify: `templates/dashboard.js` (filterData Projekt-Aggregation Zeile 595, renderProjectTable Zelle ca. Zeile 1606)

**Interfaces:**
- Consumes: `s.file_size_mb` (pro Session, Server-seitig auf 2 Dezimalstellen gerundet).
- Produces: `F.projects[].file_size_mb` = Summe der Session-Dateigroessen des Projekts.

Bewusste Abweichung von der urspruenglichen Fix-Idee "noFilter-Pfad nutzt D.projects": `F.projects` wird heute in JEDEM Modus client-seitig aus Sessions gebaut, und die Server-Projektliste zaehlt leere Sessions mit, waehrend die Client-Liste sie bei aktivem hideEmpty ausschliesst. Ein zweiter Datenpfad wuerde also genau die Sorte Basis-Drift einfuehren, die dieser Plan an anderer Stelle beseitigt. Die Summe der Session-Werte weicht von der Server-Bytesumme nur um Rundungsreste ab (<= 0.01 MB pro Session) und ist bei 1 Nachkommastelle Anzeige irrelevant.

- [ ] **Step 1: Aggregation umstellen**

In `templates/dashboard.js`, ersetze:

```js
    p.file_size_mb = Math.max(p.file_size_mb, s.file_size_mb || 0);
```

durch:

```js
    p.file_size_mb += s.file_size_mb || 0;
```

- [ ] **Step 2: Anzeige runden (Float-Summen erzeugen sonst 12.299999-Artefakte)**

In `templates/dashboard.js`, ersetze:

```js
      {val: String(p.file_size_mb), cls: 'num', label: 'File Size'},
```

durch:

```js
      {val: (p.file_size_mb || 0).toFixed(1), cls: 'num', label: 'File Size'},
```

- [ ] **Step 3: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 4: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): project file size sums session sizes instead of taking the max"
```

---

### Task 12: noFilter-Fast-Path greift im Default-Load (Finding 41a, dokumentiert F12-Client)

**Voraussetzung:** Teilplan A ist gemerged (Server-Tagesserien = Default-Ansicht-Semantik: leere Sessions ausgeschlossen, Boxplot messages >= 3). Vorher NICHT ausfuehren, sonst nimmt der Fast-Path Serien mit alter Semantik.

**Files:**
- Modify: `templates/dashboard.js` (filterData, noFilter-Bedingung + Kommentar, ca. Zeile 458-462)

**Interfaces:**
- Consumes: Server-Serien `D.daily_costs`/`D.daily_tokens`/`D.daily_messages`/`D.daily_cache_efficiency` mit Default-Ansicht-Semantik (Kontrakt Teilplan A).
- Produces: Beim Initial-Load (All time, kein Projektfilter, hideEmptySessions checked = Default) nimmt filterData die Server-Serien direkt statt alles neu zu rechnen.

Hintergrund: `hideEmptySessions` ist in dashboard.html default-checked; die alte Bedingung `!hideEmpty` machte den Fast-Path damit im Auslieferungszustand tot und der Client rechnete per Default alles neu (Perf + Drift-Risiko). Was `hideEmpty` sonst beeinflusst, wurde geprueft: (a) `F.sessions`-Filterung (Zeile 435, unabhaengig von noFilter, bleibt unveraendert), (b) die Tagesserien-Neuberechnung (uebernimmt jetzt der Server mit identischer Semantik), (c) Hour/Weekday-Distributionen (per-Message gebaut; leere Sessions haben keine Messages, tragen also in beiden Pfaden nichts bei). Der Client-Rebuild-Pfad selbst (inkl. Boxplot-Regel messages >= 3 pro Slice bei Multi-Day bzw. pro Session bei Single-Day, Zeilen 524 und 542) bleibt UNVERAENDERT; er ist die Referenzimplementierung derselben Regel und laeuft weiterhin fuer jede Nicht-Default-Kombination.

- [ ] **Step 1: Bedingung und Kommentar umstellen**

In `templates/dashboard.js`, ersetze:

```js
  // Daily aggregates. Unfiltered default view: use the server-prepared
  // per-day series directly (no client recompute). Filtered view: rebuild
  // from sessions, distributing each multi-day session across its actual
  // activity days via s.per_day (single-day sessions fall back to s.date).
  const noFilter = currentDays === 0 && !pf && !hideEmpty;
```

durch:

```js
  // Daily aggregates. Default view (all time, no project filter, empty
  // sessions hidden - the checkbox's initial state): use the server-prepared
  // per-day series directly, which are built with the same semantics (empty
  // sessions excluded, cache-eff boxplot only counts entries with
  // messages >= 3). Any other combination: rebuild from sessions,
  // distributing each multi-day session across its actual activity days via
  // s.per_day (single-day sessions fall back to s.date).
  const noFilter = currentDays === 0 && !pf && !!hideEmpty;
```

- [ ] **Step 2: Hinweis fuer die Verifikation**

Kein Code-Schritt. Die Verhaltenspruefung dieses Tasks laeuft in Task 14: Die Default-Ansicht rendert dann aus den Server-Serien (Fast-Path aktiv) und muss konsolenfehlerfrei bleiben; ebenso ein Filter-Wechsel auf 7D (Client-Rebuild) und zurueck auf All (wieder Fast-Path).

- [ ] **Step 3: Syntax-Preflight**

Run: `node --check templates/dashboard.js`
Expected: kein Output, Exit-Code 0.

- [ ] **Step 4: Commit**

```bash
git status --short
git add templates/dashboard.js
git commit -m "fix(dashboard): server-prepared daily series drive the default view (noFilter fast path)"
```

---

### Task 13: Toten Code entfernen (Finding 36) + data-sort-Attribute (HTML)

**Files:**
- Modify: `templates/dashboard.js` (8 Loeschstellen)
- Modify: `templates/dashboard.html` (Zeile 199-205, data-sort-Attribute)

**Interfaces:**
- Consumes: nichts.
- Produces: nichts Neues; entfernt nur Symbole ohne Aufrufer. Lebende Kopien von `effStyle` in templates/session_detail.js und templates/components/session_table.js bleiben UNBERUEHRT (eigene Scopes, eigene Dateien).
- Koordination: Die Loeschung des configInfo-Blocks verwaist die Locale-Keys `insights.permission_mode`, `insights.auto_updates`, `insights.plugins_installed`, `insights.plugins_active`. NICHT hier loeschen; Teilplan D (i18n) raeumt tote Keys gesammelt auf und hat diese vier bereits auf der Liste.

Jede Loeschung folgt demselben Muster: erst Grep-Beweis, dann loeschen. Wenn ein Grep unerwartete Treffer zeigt: dieses Symbol NICHT loeschen, im Report vermerken, weiter mit dem naechsten.

- [ ] **Step 1: Grep-Beweise fuer alle Kandidaten**

Run:
```bash
for sym in switchTab vcSection vcDistbar vcStatRows vcMiscGrid vcAnonWrap chartColors buildVcChartColors MODEL_COLORS makeSourceBadge sessionCacheEff envInfo; do echo "== $sym"; grep -rn "\b$sym\b" templates/ | grep -v "\.css:"; done
grep -rn "\beffStyle\b" templates/dashboard.js
grep -rn "configInfo\|systemInfo" templates/dashboard.html templates/dashboard.js
grep -rn "querySelector.*data-sort\b\|dataset\.sort\b" templates/
```
Expected: jedes Symbol hat NUR seine Definitionszeile(n) in templates/dashboard.js (chartColors: Definition + Nutzung in der eigenen Zuweisungszeile; MODEL_COLORS: Kommentarzeile + Shim-Definition; envInfo: nur der systemInfo-Block). `effStyle` in dashboard.js: nur Zeile ~61 (Definition). `configInfo`/`systemInfo`: keine Treffer in dashboard.html (Ziel-Elemente existieren nicht), nur die JS-Bloecke. `data-sort` als Attribut-Selektor/dataset.sort: 0 Treffer (nur `dataset.sortValue` existiert, das ist ein anderes Attribut).

- [ ] **Step 2: sessionCacheEff + effStyle (dashboard.js-Kopien) loeschen**

In `templates/dashboard.js`, ersetze:

```js
// Cache efficiency: cache_read / (input + cache_read + cache_write).
// Returns null when the session has no input-side tokens recorded.
function sessionCacheEff(s) {
  const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
  if (inputSum === 0) return null;
  return (s.cache_read_tokens||0) / inputSum * 100;
}
function effStyle(pct) {
  if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
  if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
  if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
  return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
}

```

durch (nichts, Block ersatzlos entfernen; die Leerzeile am Blockende gehoert zum old_string):

```js

```

- [ ] **Step 3: MODEL_COLORS-Shim loeschen, Kommentar anpassen**

In `templates/dashboard.js`, ersetze:

```js
// MODEL_COLORS: explicit per-model palette built around three on-brand
```

durch:

```js
// Per-model chart palette built around three on-brand
```

und ersetze:

```js
// Backwards-compat shim: MODEL_COLORS[m] still works for existing code.
const MODEL_COLORS = {
  get _proxy() { return true; },
};
['Fable 5', 'Opus 4.8', 'Opus 4.7', 'Opus 4.6', 'Opus 4.5', 'Sonnet 4.6', 'Sonnet 4.5', 'Sonnet 4.0', 'Haiku 4.5', 'Haiku 3.5', 'Unknown'].forEach(m => {
  Object.defineProperty(MODEL_COLORS, m, { get() { return vcModelColor(m); }, enumerable: true });
});

```

durch:

```js

```

- [ ] **Step 4: makeSourceBadge loeschen**

In `templates/dashboard.js`, ersetze:

```js
function makeSourceBadge(label) {
  const c = sourceColor(label);
  const span = document.createElement('span');
  span.className = 'source-badge';
  span.style.background = c.bg; span.style.color = c.fg;
  span.textContent = label;
  return span;
}

```

durch:

```js

```

(`sourceColor` selbst bleibt: renderProjectTable nutzt es inline.)

- [ ] **Step 5: buildVcChartColors + chartColors loeschen**

In `templates/dashboard.js`, ersetze:

```js
// Variant-C: 10-slot palette using accent + fg shades cycled.
// Plain array rebuilt on demand to avoid Proxy-array compat issues with Chart.js.
function buildVcChartColors(n) {
  n = n || 10;
  const out = [vcColor(0), vcColor(1), vcColor(2)];
  for (let i = 3; i < n; i++) out.push(vcRgba(0, Math.max(0.15, 1 - i * 0.1)));
  return out;
}
const chartColors = buildVcChartColors(13);
```

durch (nichts; die Nachbarzeile `let currentProjectFilter = '';` bleibt unveraendert stehen):

```js
```

- [ ] **Step 6: switchTab loeschen**

In `templates/dashboard.js`, ersetze:

```js
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

```

durch:

```js

```

- [ ] **Step 7: configInfo-Block loeschen (Ziel-Element existiert nicht im HTML)**

In `templates/dashboard.js`, ersetze:

```js
  // Config info
  // Storage rows intentionally omitted here — the chartStorage doughnut above is
  // the single source for the storage breakdown, so we don't duplicate it.
  const configDiv = document.getElementById('configInfo');
  const settings = plugins.settings || {};
  const configItems = [
    {label: D.locale.insights.permission_mode, value: settings.permission_mode || '-'},
    {label: D.locale.insights.auto_updates, value: settings.auto_updates || '-'},
    {label: D.locale.insights.plugins_installed, value: String(installed.length)},
    {label: D.locale.insights.plugins_active, value: String(Object.values(enabled).filter(v => v).length)},
  ];
  const grid = document.createElement('div'); grid.className = 'config-grid';
  configItems.forEach(c => {
    const item = document.createElement('div'); item.className = 'config-item';
    const lbl = document.createElement('div'); lbl.className = 'ci-label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'ci-value'; val.textContent = c.value;
    item.appendChild(lbl); item.appendChild(val);
    grid.appendChild(item);
  });
  if (configDiv) configDiv.appendChild(grid);   // Environment section was removed; guard the (now absent) target

```

durch:

```js

```

- [ ] **Step 8: systemInfo-Block loeschen (Ziel-Element existiert nicht im HTML)**

In `templates/dashboard.js`, ersetze:

```js
  // System info
  const envInfo = D.insights?.telemetry?.env_info || {};
  const sysEl = document.getElementById('systemInfo');
  if (sysEl) {
    sysEl.innerHTML =
      '<div class="sidebar-row"><span class="label">Platform</span><span class="val">'+(envInfo.platform||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Node</span><span class="val">'+(envInfo.node_version||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Claude Code</span><span class="val">'+(envInfo.claude_version||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Terminal</span><span class="val">'+(envInfo.terminal||'\\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Arch</span><span class="val">'+(envInfo.arch||'\\u2014')+'</span></div>';
  }

```

durch:

```js

```

- [ ] **Step 9: Variant-C-Helfer-Block loeschen**

In `templates/dashboard.js`, ersetze:

```js
// ── Variant-C shared render helpers ───────────────────────────────
function vcSection(title, meta) {
  const h = document.createElement('div');
  h.className = 'vc-tab-h';
  const t = document.createElement('div'); t.className = 'vc-tab-h-title';
  t.textContent = title;
  const r = document.createElement('div'); r.className = 'vc-tab-h-rule';
  const m = document.createElement('div'); m.className = 'vc-tab-h-meta'; m.textContent = meta || '';
  h.appendChild(t); h.appendChild(r); h.appendChild(m);
  return h;
}

function vcDistbar(rows, opts) {
  opts = opts || {};
  const max = opts.max || Math.max.apply(null, rows.map(function(r){return r.value||0}).concat([1]));
  const series = opts.series || 1;
  const seriesClass = series === 2 ? 's2' : (series === 3 ? 's3' : '');
  const c = document.createElement('div'); c.className = 'vc-distbar';
  rows.forEach(function(r){
    const row = document.createElement('div'); row.className = 'vc-distbar-row';
    const n = document.createElement('div'); n.className = 'vc-distbar-name'; n.textContent = r.name;
    if (opts.anonName) n.classList.add('anon-blur');
    const t = document.createElement('div'); t.className = 'vc-distbar-track';
    const f = document.createElement('div'); f.className = 'vc-distbar-fill ' + seriesClass;
    const v = (r.value || 0);
    f.style.width = (max > 0 ? (v / max * 100) : 0).toFixed(1) + '%';
    t.appendChild(f);
    const val = document.createElement('div'); val.className = 'vc-distbar-val';
    val.textContent = r.label != null ? r.label : v.toLocaleString('en-US');
    row.appendChild(n); row.appendChild(t); row.appendChild(val);
    c.appendChild(row);
  });
  return c;
}

function vcStatRows(rows) {
  const c = document.createDocumentFragment();
  rows.forEach(function(r){
    const row = document.createElement('div'); row.className = 'vc-stat-row';
    const k = document.createElement('div'); k.className = 'k'; k.textContent = r.k;
    const v = document.createElement('div'); v.className = 'v' + (r.acc ? ' acc' : '');
    if (r.html) { v.innerHTML = r.html; } else { v.textContent = r.v; }
    if (r.title) row.title = r.title;
    row.appendChild(k); row.appendChild(v);
    c.appendChild(row);
  });
  return c;
}

function vcMiscGrid(items) {
  const c = document.createElement('div'); c.className = 'vc-misc-grid';
  items.forEach(function(it){
    const m = document.createElement('div'); m.className = 'vc-misc';
    const v = document.createElement('div'); v.className = 'v' + (it.acc ? ' acc' : '');
    v.textContent = it.v;
    const l = document.createElement('div'); l.className = 'l'; l.textContent = it.l;
    m.appendChild(v); m.appendChild(l);
    c.appendChild(m);
  });
  return c;
}

// Wrap unpredictable text content (for anon-mode CSS blur)
function vcAnonWrap(text) {
  const s = document.createElement('span');
  s.className = 'anon-blur';
  s.textContent = text;
  return s;
}

```

durch:

```js

```

- [ ] **Step 10: data-sort-Attribute im projectTable-Header entfernen**

In `templates/dashboard.html`, ersetze:

```html
          <th data-sort="name">__L_projects_th_project__</th>
          <th data-sort="sources">Source</th>
          <th data-sort="sessions" class="num">__L_projects_th_sessions__</th>
          <th data-sort="messages" class="num">__L_projects_th_messages__</th>
          <th data-sort="cost" class="num">__L_projects_th_api_value__</th>
          <th data-sort="output_tokens" class="num">__L_projects_th_output_tokens__</th>
          <th data-sort="file_size_mb" class="num">__L_projects_th_file_size__</th>
```

durch:

```html
          <th>__L_projects_th_project__</th>
          <th>Source</th>
          <th class="num">__L_projects_th_sessions__</th>
          <th class="num">__L_projects_th_messages__</th>
          <th class="num">__L_projects_th_api_value__</th>
          <th class="num">__L_projects_th_output_tokens__</th>
          <th class="num">__L_projects_th_file_size__</th>
```

(Sortierung laeuft unveraendert ueber attachTableSorting per Spaltenindex; die Attribute hatten keinen Konsumenten.)

- [ ] **Step 11: Nachweis, dass nichts Referenziertes geloescht wurde**

Run:
```bash
node --check templates/dashboard.js
for sym in switchTab vcSection vcDistbar vcStatRows vcMiscGrid vcAnonWrap chartColors buildVcChartColors MODEL_COLORS makeSourceBadge sessionCacheEff; do grep -rn "\b$sym\b" templates/dashboard.js; done
```
Expected: node --check ohne Output; alle Greps 0 Treffer (effStyle-Kopien in session_detail.js/session_table.js existieren weiter, das ist korrekt).

- [ ] **Step 12: Commit**

```bash
git status --short
git add templates/dashboard.js templates/dashboard.html
git commit -m "refactor(dashboard): remove dead code (unused helpers, void-rendering blocks, vestigial data-sort attrs)"
```

---

### Task 14: Integrations-Smoke: Extractor + Headless Chromium + pytest

**Files:**
- Keine Aenderungen; reiner Verifikations-Task. Bei Fehlern: verursachenden Task identifizieren, dort fixen, diesen Task wiederholen.

**Interfaces:**
- Consumes: alle vorherigen Tasks.
- Produces: verifizierter Endzustand des Teilplans.

Hinweis: Chart.js laedt per CDN (dashboard.html Zeile 12-13). Der Headless-Test braucht Netz; erscheint `Chart is not defined` in der Konsole, zuerst die Netzverbindung pruefen, bevor es als Regression gilt.

- [ ] **Step 1: Backend-Suite**

Run: `python3 -m pytest tests/ -q`
Expected: alle Tests bestehen (`... passed`, 0 failed). Dieser Plan aendert kein Python; Failures kaemen aus Teilplan A oder paralleler Arbeit: melden, nicht selbst fixen.

- [ ] **Step 2: Dashboard generieren**

Run: `python3 extract_stats.py`
Expected: Lauf endet ohne Traceback; `public/index.html` hat frischen Zeitstempel (`ls -la public/index.html`).

- [ ] **Step 3: Headless-Chromium-Smoke**

Run:
```bash
CHROME="$HOME/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
"$CHROME" --headless=new --disable-gpu --no-sandbox --virtual-time-budget=8000 \
  --enable-logging=stderr --dump-dom "file://$(pwd)/public/index.html" \
  > /tmp/claude-smoke-dom.html 2> /tmp/claude-smoke-console.log
echo "exit: $?"
```
Expected: exit 0, /tmp/claude-smoke-dom.html mehrere hundert KB gross.

- [ ] **Step 4: Konsole und DOM pruefen**

Run:
```bash
grep -iE "uncaught|referenceerror|typeerror|syntaxerror" /tmp/claude-smoke-console.log; echo "console-errors-grep-exit: $?"
grep -c 'id="vcKpiApiEq"' /tmp/claude-smoke-dom.html
grep -cE '>(NaN|undefined)<' /tmp/claude-smoke-dom.html; echo "nan-grep-exit: $?"
```
Expected: erster Grep leer mit Exit 1 (keine JS-Fehler); zweiter Grep `1` (KPI-Element vorhanden); dritter Grep `0` mit Exit 1 (kein NaN/undefined als Textknoten).

- [ ] **Step 5: Stichprobe KPI-Wert nicht leer**

Run: `grep -o 'id="vcKpiApiEq"[^<]*<' /tmp/claude-smoke-dom.html | head -1`
Expected: enthaelt einen formatierten Betrag (z.B. `>$1,234.56<` bzw. Lokalformat), nicht `><` und nicht `-` allein.

- [ ] **Step 6: Kein Commit**

Task 14 produziert keine Aenderungen. `git status --short` darf nur die bekannten untracked/lokalen Artefakte zeigen (public/ ist gitignored bzw. lokal; nichts stagen).

---

## Selbst-Review-Protokoll (bei Planerstellung durchgefuehrt)

- Spec-Abdeckung: F4 -> Task 1; F6 -> Task 2; F5 -> Task 3; F22 -> Task 4; F21 -> Task 5; F13-Frontend -> Task 6; F14 -> Task 7; F20 -> Task 8; F39-Teil -> Task 9; F8-Frontend-Pendant -> Task 10; F10 -> Task 11; 41a + F12-Client -> Task 12; F36 + data-sort -> Task 13; Gesamtverifikation -> Task 14. Kein Finding aus dem B-Scope offen.
- Platzhalter-Scan: keine TODO/TBD/"analog zu"-Stellen; jeder Code-Step traegt den vollstaendigen Code.
- Typ-/Namenskonsistenz: `weekAnchorDayNum` (Task 6) wird nur dort definiert und genutzt; `errorRateChartInstance`/`taskDonutChartInstance` werden in Task 8 Step 1 gemeinsam deklariert und in Task 8/9 genutzt (Task 9 setzt Task 8 voraus; Reihenfolge im Plan entspricht dem); `cumRows` ersetzt `cumSrc` vollstaendig (Grep-Step vorhanden). Task 1 laesst `dates` bewusst stehen (Konsument first_session/last_session).
- Bekannte bewusste Abweichung: Task 11 nutzt KEINEN D.projects-noFilter-Pfad (Begruendung im Task dokumentiert: hideEmpty-Semantik-Drift bei Session-Zaehlern, einheitlicher Datenpfad).
