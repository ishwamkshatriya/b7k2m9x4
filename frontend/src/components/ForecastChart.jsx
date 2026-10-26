import React from 'react';

const WIDTH = 940;
const HEIGHT = 290;
const PAD = { top: 22, right: 22, bottom: 42, left: 66 };
const fmt = (value) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(value);

function buildPath(points, key, x, y) {
  let path = '';
  let active = false;
  points.forEach((point, index) => {
    const value = point[key];
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      active = false;
      return;
    }
    const command = active ? 'L' : 'M';
    path += `${command}${x(index).toFixed(2)},${y(Number(value)).toFixed(2)} `;
    active = true;
  });
  return path.trim();
}

export default function ForecastChart({ records = [], unit = 'MW' }) {
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const rows = records;
  const hasPair = rows.some((row) => row.pairStatus === 'paired');
  const allValues = rows.flatMap((row) => [row.forecastGeneration, row.actualGeneration]).filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  if (!hasPair || !allValues.length) {
    return <div className="chart-empty"><div className="empty-glyph">↗</div><strong>No matched hourly series yet</strong><span>Load the complete Elexon snapshot to plot the forecast beside hourly actual outturn.</span></div>;
  }

  const minValue = Math.min(0, ...allValues);
  const maxValue = Math.max(...allValues);
  const range = Math.max(maxValue - minValue, 1);
  const yMin = minValue - range * 0.06;
  const yMax = maxValue + range * 0.08;
  const x = (index) => PAD.left + (rows.length <= 1 ? plotWidth / 2 : index * plotWidth / (rows.length - 1));
  const y = (value) => PAD.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
  const forecastPath = buildPath(rows, 'forecastGeneration', x, y);
  const actualPath = buildPath(rows, 'actualGeneration', x, y);
  const ticks = Array.from({ length: 5 }, (_, index) => yMax - ((yMax - yMin) * index / 4));
  const labels = [0, Math.floor((rows.length - 1) / 2), rows.length - 1].filter((n, idx, arr) => arr.indexOf(n) === idx);

  return (
    <div className="chart-wrap">
      <div className="chart-legend">
        <span><i className="legend-dot forecast-dot" /> Decision-time forecast</span>
        <span><i className="legend-dot actual-dot" /> Actual hourly mean</span>
        <small>Generation ({unit})</small>
      </div>
      <svg className="line-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Hourly wind generation forecast compared with actual generation">
        {ticks.map((tick, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="chart-gridline" />
            <text x={PAD.left - 12} y={y(tick) + 4} textAnchor="end" className="chart-tick">{fmt(tick)}</text>
          </g>
        ))}
        <path d={forecastPath} className="forecast-line" />
        <path d={actualPath} className="actual-line" />
        {labels.map((index) => (
          <g key={index}>
            <line x1={x(index)} x2={x(index)} y1={HEIGHT - PAD.bottom} y2={HEIGHT - PAD.bottom + 5} className="chart-axis" />
            <text x={x(index)} y={HEIGHT - 13} textAnchor={index === 0 ? 'start' : index === rows.length - 1 ? 'end' : 'middle'} className="chart-tick">{rows[index]?.deliveryStartLocal?.slice(0, 16).replace('T', ' ') || rows[index]?.deliveryDate}</text>
          </g>
        ))}
      </svg>
      <div className="chart-footnote">{rows.length.toLocaleString('en-GB')} hourly delivery slots in view. Missing values break the lines rather than being interpolated.</div>
    </div>
  );
}
