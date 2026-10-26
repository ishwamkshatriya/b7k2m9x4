import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ForecastChart from './components/ForecastChart.jsx';
import DailyAccuracyChart from './components/DailyAccuracyChart.jsx';

const API = '/api/v1';
const number = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value))
  ? '—'
  : Number(value).toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (value) => value === null || value === undefined ? '—' : `${number(value, 1)}%`;

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
  const paths = {
    wind: <><path d="M3 8h12.5a2.5 2.5 0 1 0-2.4-3.2"/><path d="M2 12h17a2.5 2.5 0 1 1-2.4 3.2"/><path d="M4 16h6.5a2.2 2.2 0 1 1-2.1 2.8"/></>,
    pulse: <><path d="M3 12h4l2.5-6 4.5 12 2.5-6H21"/></>,
    target: <><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><path d="M12 2v3M22 12h-3M12 22v-3M2 12h3"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></>,
    chart: <><path d="M3 3v18h18"/><path d="m7 14 4-4 3 2 5-7"/></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5"/><path d="M5 17v4h14v-4"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9a6.5 6.5 0 0 1 11-2L20 12M4 12l2.9 5a6.5 6.5 0 0 0 11-2"/></>,
    alert: <><path d="m12 3 9 17H3L12 3Z"/><path d="M12 9v5m0 3h.01"/></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10"/></>,
  };
  return <svg {...common}>{paths[name] || paths.chart}</svg>;
}

function MetricCard({ label, value, unit, hint, icon, tone = 'mint' }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon name={icon} size={19} /></div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}<span>{unit || ''}</span></div>
      <div className="metric-hint">{hint}</div>
    </article>
  );
}

function StatusPill({ quality }) {
  const complete = quality?.snapshotComplete;
  const partial = quality?.status !== 'ok';
  const label = complete ? (partial ? 'DATA PARTIAL' : 'SNAPSHOT READY') : quality?.source === 'sample_fixture' ? 'SAMPLE DATA ONLY' : 'SNAPSHOT NOT READY';
  return <span className={`status-pill ${complete && !partial ? 'good' : 'warn'}`}><i />{label}</span>;
}

function CoverageBar({ label, value, subtext }) {
  const width = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="coverage-row">
      <div className="coverage-top"><span>{label}</span><strong>{pct(value)}</strong></div>
      <div className="coverage-track"><div className="coverage-fill" style={{ width: `${width}%` }} /></div>
      <div className="coverage-subtext">{subtext}</div>
    </div>
  );
}

function fmtDateTime(value) {
  if (!value) return '—';
  return value.replace('T', ' ').replace('Z', ' UTC').slice(0, 22);
}

function csvEscape(value) {
  const text = value === null || value === undefined ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export default function App() {
  const [config, setConfig] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [startDate, setStartDate] = useState('2026-01-01');
  const [endDate, setEndDate] = useState('2026-01-31');
  const [cutoff, setCutoff] = useState('12:00');
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastLoaded, setLastLoaded] = useState(null);

  const load = useCallback(async (params = {}) => {
    const nextStart = params.startDate ?? startDate;
    const nextEnd = params.endDate ?? endDate;
    const nextCutoff = params.cutoff ?? cutoff;
    setLoading(true);
    setError('');
    try {
      const [configResponse, analysisResponse] = await Promise.all([
        fetch(`${API}/config`),
        fetch(`${API}/analysis?${new URLSearchParams({ startDecisionDate: nextStart, endDecisionDate: nextEnd, cutoffTime: nextCutoff })}`),
      ]);
      const configBody = await configResponse.json();
      const analysisBody = await analysisResponse.json();
      if (!configResponse.ok) throw new Error(configBody.message || 'Could not read application configuration.');
      if (!analysisResponse.ok) throw new Error(analysisBody.message || analysisBody.detail || 'Analysis request failed.');
      setConfig(configBody);
      setAnalysis(analysisBody);
      setLastLoaded(new Date());
    } catch (err) {
      setError(err?.message || 'Unable to connect to the backend.');
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, cutoff]);

  useEffect(() => { load(); }, []); // Initial API load only; filter changes are submitted explicitly.

  const filteredRows = useMemo(() => {
    const records = analysis?.records || [];
    const q = search.trim().toLowerCase();
    return records.filter((row) => {
      if (statusFilter === 'paired' && row.pairStatus !== 'paired') return false;
      if (statusFilter === 'missing' && row.pairStatus === 'paired') return false;
      if (!q) return true;
      return [row.deliveryStartUtc, row.deliveryDate, row.forecastStatus, row.actualStatus, row.pairStatus]
        .some((value) => String(value ?? '').toLowerCase().includes(q));
    });
  }, [analysis, statusFilter, search]);

  const tableRows = useMemo(() => {
    const items = [...filteredRows];
    if (statusFilter === 'all' && !search.trim()) {
      items.sort((a, b) => {
        const av = a.absoluteError === null ? -1 : Number(a.absoluteError);
        const bv = b.absoluteError === null ? -1 : Number(b.absoluteError);
        return bv - av;
      });
    }
    return items.slice(0, 18);
  }, [filteredRows, statusFilter, search]);

  function applyFilters(event) {
    event.preventDefault();
    load({ startDate, endDate, cutoff });
  }

  function exportCsv() {
    const rows = analysis?.records || [];
    const headers = ['decisionDate', 'deliveryDate', 'deliveryStartUtc', 'decisionCutoffUtc', 'forecastPublishTimeUtc', 'forecastGeneration', 'actualGeneration', 'error', 'absoluteError', 'forecastLeadTimeMinutes', 'forecastStatus', 'actualStatus', 'pairStatus'];
    const body = [headers.join(','), ...rows.map((row) => headers.map((key) => csvEscape(row[key])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'wind-forecast-analysis-january-2026.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  const metrics = analysis?.metrics || {};
  const coverage = analysis?.coverage || {};
  const quality = analysis?.dataQuality || {};
  const hasSnapshot = Boolean(quality.snapshotComplete);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><span /><span /><span /></div>
          <div><div className="brand-name">WIND<span>INTEL</span></div><div className="brand-caption">ENERGY ANALYTICS</div></div>
        </div>
        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Primary navigation">
          <a href="#overview" className="nav-item active"><Icon name="chart" /><span>Overview</span><b>01</b></a>
          <a href="#accuracy" className="nav-item"><Icon name="pulse" /><span>Accuracy analysis</span></a>
          <a href="#records" className="nav-item"><Icon name="layers" /><span>Delivery records</span></a>
          <a href="#methodology" className="nav-item"><Icon name="target" /><span>Methodology</span></a>
        </nav>
        <div className="sidebar-bottom">
          <div className="source-card">
            <div className="source-card-head"><span className="source-indicator" /> DATA SOURCES</div>
            <div className="source-entry"><span className="source-monogram">W</span><div><strong>WINDFOR</strong><small>Hourly forecast stream</small></div></div>
            <div className="source-entry"><span className="source-monogram actual">A</span><div><strong>FUELHH</strong><small>Half-hourly actuals · WIND</small></div></div>
            <div className="source-separator" />
            <div className="source-foot"><Icon name="clock" size={14} /> Historical replay · Jan 2026</div>
          </div>
          <div className="sidebar-footnote">PILOT WORKSPACE <span>v1.0.0</span></div>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>Wind forecast intelligence</strong></div>
          <div className="topbar-right"><span className="env-badge"><i /> HISTORICAL ANALYSIS</span><div className="avatar">WI</div></div>
        </header>

        <section className="page-intro">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> NATIONAL WIND · GREAT BRITAIN</div>
            <h1>Forecast intelligence<span>.</span></h1>
            <p className="intro-copy">Understand what the buyer could know at decision time — and how the forecast compared with actual generation.</p>
          </div>
          <div className="intro-meta"><div className="meta-label">ANALYSIS WINDOW</div><div className="meta-value">01 — 31 <span>JAN 2026</span></div><div className="meta-note">Decision dates · next-day delivery</div></div>
        </section>

        <section className="filter-panel" aria-label="Analysis filters">
          <div className="filter-heading"><div className="filter-heading-icon"><Icon name="target" /></div><div><strong>Decision replay</strong><span>Configure the historical information cutoff</span></div><StatusPill quality={quality} /></div>
          <form className="filter-form" onSubmit={applyFilters}>
            <label><span>Decision date from</span><input type="date" min="2026-01-01" max="2026-01-31" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label>
            <label><span>Decision date to</span><input type="date" min="2026-01-01" max="2026-01-31" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></label>
            <label className="cutoff-field"><span>Decision cutoff <em>Europe/London</em></span><input type="time" value={cutoff} onChange={(e) => setCutoff(e.target.value)} /></label>
            <button className="primary-button" type="submit" disabled={loading}><Icon name="refresh" size={16} />{loading ? 'Analysing…' : 'Apply filters'}</button>
          </form>
          <div className="filter-foot"><span><Icon name="alert" size={14} /> 12:00 is an illustrative cutoff, not a confirmed market deadline.</span><span>DELIVERY = DECISION DATE + 1 DAY</span></div>
        </section>

        {!hasSnapshot && !loading && (
          <section className="snapshot-notice" role="status">
            <div className="notice-icon"><Icon name="alert" size={20} /></div>
            <div className="notice-body"><strong>Full-month snapshot not loaded</strong><p>This starter package contains only three genuine sample records from each Elexon endpoint. The dashboard does not calculate or display fabricated monthly accuracy figures.</p><code>python scripts/refresh_snapshot.py</code><p className="notice-small">Run the command from the project root on a machine with Elexon API access, then refresh the page. The script will save the real January decision/delivery snapshot.</p></div>
          </section>
        )}

        {error && <div className="error-banner"><Icon name="alert" /><div><strong>Could not load analysis</strong><span>{error}</span></div><button type="button" onClick={() => load()}>Retry</button></div>}

        <section className="section-block" aria-label="Accuracy summary">
          <div className="section-heading"><div><div className="section-kicker">PERFORMANCE SNAPSHOT</div><h2>Accuracy at a glance</h2></div><div className="section-aside">{loading ? 'Refreshing data…' : `${number(metrics.n)} valid hourly pairs`}<span className="aside-dot" /></div></div>
          <div className="metrics-grid">
            <MetricCard label="Mean absolute error" value={number(metrics.mae, 1)} unit={metrics.mae == null ? '' : ` ${analysis?.methodology?.unit || 'MW'}`} hint="Average absolute forecast miss" icon="pulse" tone="mint" />
            <MetricCard label="Root mean squared error" value={number(metrics.rmse, 1)} unit={metrics.rmse == null ? '' : ` ${analysis?.methodology?.unit || 'MW'}`} hint="Highlights larger misses" icon="chart" tone="blue" />
            <MetricCard label="Forecast bias" value={number(metrics.bias, 1)} unit={metrics.bias == null ? '' : ` ${analysis?.methodology?.unit || 'MW'}`} hint={metrics.bias == null ? 'Positive = overforecast' : Number(metrics.bias) > 0 ? 'Net overforecast' : Number(metrics.bias) < 0 ? 'Net underforecast' : 'No net signed bias'} icon="target" tone="violet" />
            <MetricCard label="Paired coverage" value={pct(coverage.pairedCoveragePct)} unit="" hint={`${number(coverage.pairedIntervals)} of ${number(coverage.expectedComparisons)} hourly comparisons`} icon="layers" tone="amber" />
          </div>
          <div className="secondary-metrics">
            <div><span>P95 absolute error</span><strong>{number(metrics.p95AbsoluteError, 1)}{metrics.p95AbsoluteError == null ? '' : ` ${analysis?.methodology?.unit || 'MW'}`}</strong></div>
            <div><span>Maximum absolute error</span><strong>{number(metrics.maxAbsoluteError, 1)}{metrics.maxAbsoluteError == null ? '' : ` ${analysis?.methodology?.unit || 'MW'}`}</strong></div>
            <div><span>Average forecast lead</span><strong>{number(rowsMeanLead(analysis?.records), 0)} <small>min</small></strong></div>
            <div><span>Hourly intervals expected</span><strong>{number(coverage.expectedComparisons)}</strong></div>
          </div>
        </section>

        <section className="analysis-grid" id="accuracy">
          <article className="panel forecast-panel">
            <div className="panel-heading"><div><div className="section-kicker">HOURLY SERIES</div><h2>Forecast vs actual</h2><p>Decision-time forecast compared with hourly mean of actual wind outturn.</p></div><span className="panel-chip">60 MIN</span></div>
            <ForecastChart records={analysis?.records || []} unit={analysis?.methodology?.unit || 'MW'} />
          </article>
          <article className="panel daily-panel">
            <div className="panel-heading"><div><div className="section-kicker">DAY-BY-DAY</div><h2>Daily forecast error</h2><p>Mean absolute error by purchasing decision date.</p></div><span className="panel-chip">MAE</span></div>
            <DailyAccuracyChart daily={analysis?.daily || []} unit={analysis?.methodology?.unit || 'MW'} />
          </article>
        </section>

        <section className="lower-grid">
          <article className="panel coverage-panel">
            <div className="panel-heading"><div><div className="section-kicker">DATA CONFIDENCE</div><h2>Coverage & quality</h2><p>Completeness is reported separately from accuracy.</p></div><Icon name="layers" size={20} /></div>
            <div className="coverage-list">
              <CoverageBar label="Eligible forecasts" value={coverage.forecastCoveragePct} subtext={`${number(coverage.eligibleForecastSlots)} valid hourly forecasts / ${number(coverage.expectedForecastSlots)} expected`} />
              <CoverageBar label="Actual hourly values" value={coverage.actualCoveragePct} subtext={`${number(coverage.actualHourlySlotsComplete)} hours with both half-hour actuals`} />
              <CoverageBar label="Paired comparisons" value={coverage.pairedCoveragePct} subtext={`${number(coverage.pairedIntervals)} valid pairs available for accuracy metrics`} />
              <CoverageBar label="Raw half-hour actuals" value={coverage.actualHalfHourCoveragePct} subtext={`${number(coverage.actualHalfHoursAvailable)} of ${number(coverage.expectedActualHalfHours)} expected half-hours`} />
            </div>
            <div className="quality-divider" />
            <div className="quality-summary"><div className={`quality-status ${quality.status === 'ok' ? 'success' : 'warning'}`}><Icon name={quality.status === 'ok' ? 'target' : 'alert'} size={16} />{quality.status === 'ok' ? 'Quality checks passed' : 'Partial coverage / validation required'}</div><div className="quality-mini-grid"><div><span>Forecast conflicts</span><strong>{number(coverage.forecastConflicts)}</strong></div><div><span>Missing forecasts</span><strong>{number(coverage.missingForecasts)}</strong></div><div><span>Missing actual hours</span><strong>{number(coverage.missingActualHourlySlots)}</strong></div></div></div>
            {(quality.messages || []).length > 0 && <ul className="quality-messages">{quality.messages.slice(0, 3).map((message) => <li key={message}>{message}</li>)}</ul>}
          </article>

          <article className="panel methodology-panel" id="methodology">
            <div className="panel-heading"><div><div className="section-kicker">HOW TO READ THIS</div><h2>Methodology notes</h2><p>Assumptions that shape the headline figures.</p></div><Icon name="target" size={20} /></div>
            <div className="method-item"><div className="method-number">01</div><div><strong>Point-in-time selection</strong><p>For each delivery hour, the newest forecast with <code>publishTime ≤ decision cutoff</code> is selected. Later forecast versions are excluded.</p></div></div>
            <div className="method-item"><div className="method-number">02</div><div><strong>Hourly / half-hourly alignment</strong><p>WINDFOR is hourly. FUELHH is half-hourly. The comparison uses the mean of both half-hour actuals; both must be present. This is an explicit analytical assumption.</p></div></div>
            <div className="method-item"><div className="method-number">03</div><div><strong>Error sign convention</strong><p><code>Forecast − actual</code>. Positive values indicate overforecasting; negative values indicate underforecasting.</p></div></div>
            <div className="method-source"><span>DATA SOURCE</span><a href="https://bmrs.elexon.co.uk/wind-generation" target="_blank" rel="noreferrer">Elexon Insights · Wind generation <Icon name="arrow" size={13} /></a><small>Forecast series cover wind farms visible to NESO with operational metering; coverage can differ from the actual generation aggregate.</small></div>
          </article>
        </section>

        <section className="panel records-panel" id="records">
          <div className="panel-heading records-heading"><div><div className="section-kicker">INTERVAL-LEVEL INSPECTION</div><h2>Delivery records</h2><p>Inspect selected publication times, paired values, and missing periods.</p></div><div className="record-actions"><button type="button" className="secondary-button" onClick={() => load()} disabled={loading}><Icon name="refresh" size={15} /> Refresh</button><button type="button" className="primary-button export-button" onClick={exportCsv} disabled={!analysis?.records?.length}><Icon name="download" size={15} /> Export CSV</button></div></div>
          <div className="table-toolbar"><div className="table-count">Showing <strong>{number(Math.min(18, filteredRows.length))}</strong> of <strong>{number(filteredRows.length)}</strong> intervals</div><div className="table-controls"><label className="search-box"><span>⌕</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search date or status" /></label><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter record status"><option value="all">All periods</option><option value="paired">Matched only</option><option value="missing">Missing / invalid</option></select></div></div>
          <div className="table-scroll"><table><thead><tr><th>Delivery start (UTC)</th><th>Forecast published (UTC)</th><th>Forecast</th><th>Actual hourly mean</th><th>Error</th><th>Forecast status</th><th>Actual status</th></tr></thead><tbody>
            {loading ? <tr><td colSpan="7" className="table-empty">Loading interval analysis…</td></tr> : tableRows.length === 0 ? <tr><td colSpan="7" className="table-empty">No records match the selected filter.</td></tr> : tableRows.map((row) => <tr key={row.deliveryStartUtc}><td className="mono">{fmtDateTime(row.deliveryStartUtc)}</td><td className="mono muted-cell">{fmtDateTime(row.forecastPublishTimeUtc)}</td><td className="numeric-cell">{number(row.forecastGeneration)}</td><td className="numeric-cell">{number(row.actualGeneration, 1)}</td><td className={`numeric-cell ${row.error > 0 ? 'error-positive' : row.error < 0 ? 'error-negative' : ''}`}>{row.error == null ? '—' : `${row.error > 0 ? '+' : ''}${number(row.error, 1)}`}</td><td><span className={`table-status ${row.forecastStatus === 'ok' ? 'status-ok' : 'status-missing'}`}>{row.forecastStatus.replaceAll('_', ' ')}</span></td><td><span className={`table-status ${row.actualStatus === 'ok' ? 'status-ok' : 'status-missing'}`}>{row.actualStatus.replaceAll('_', ' ')}</span></td></tr>)}
          </tbody></table></div>
          <div className="table-footer"><span>Rows are sorted by absolute error when showing all periods.</span><span>CSV export includes the complete filtered analysis range.</span></div>
        </section>

        <footer className="page-footer"><div>WIND<span>INTEL</span> <i>·</i> Gridbricks pilot concept</div><div>{lastLoaded ? `Last refreshed ${lastLoaded.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}` : 'Waiting for data'} <span className="footer-sep">/</span> Elexon Insights API</div></footer>
      </main>
    </div>
  );
}

function rowsMeanLead(rows = []) {
  const leads = rows.map((row) => row.forecastLeadTimeMinutes).filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)));
  return leads.length ? leads.reduce((sum, value) => sum + Number(value), 0) / leads.length : null;
}
