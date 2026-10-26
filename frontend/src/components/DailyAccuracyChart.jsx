import React from 'react';

export default function DailyAccuracyChart({ daily = [], unit = 'MW' }) {
  const valid = daily.filter((item) => item.mae !== null && item.mae !== undefined && Number.isFinite(Number(item.mae)));
  if (!valid.length) {
    return <div className="chart-empty compact"><div className="empty-glyph">▥</div><strong>Daily accuracy unavailable</strong><span>Daily error bars appear after valid forecast–actual pairs are available.</span></div>;
  }
  const max = Math.max(...valid.map((item) => Number(item.mae)), 1);
  return (
    <div className="daily-chart" role="img" aria-label="Daily mean absolute forecast error">
      <div className="daily-axis"><span>{max.toLocaleString('en-GB', { maximumFractionDigits: 0 })} {unit}</span><span>0</span></div>
      {daily.map((item) => {
        const value = item.mae === null || item.mae === undefined ? null : Number(item.mae);
        return (
          <div className={`daily-row ${value === null ? 'is-empty' : ''}`} key={item.decisionDate} title={`${item.decisionDate}: ${value === null ? 'no valid pairs' : `${value.toFixed(1)} ${unit} MAE`}`}>
            <span className="daily-label">{item.decisionDate.slice(-2)}</span>
            <div className="daily-track"><div className="daily-bar" style={{ width: `${value === null ? 0 : Math.max(0, value / max * 100)}%` }} /></div>
            <span className="daily-value">{value === null ? '—' : value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}</span>
          </div>
        );
      })}
      <div className="daily-footnote">Each bar pools valid hourly pairs within that decision date.</div>
    </div>
  );
}
