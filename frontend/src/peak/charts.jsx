// 그래프 라이브러리 없이 SVG로 그린다 (package.json을 건드리지 않기 위해).
// viewBox로 그려서 너비에 맞춰 늘어난다.

const W = 320;
const H = 160;
const PAD = { left: 34, right: 10, top: 10, bottom: 24 };

function scale(value, max, size) {
  return max > 0 ? (value / max) * size : 0;
}

function niceMax(value) {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / step) * step;
}

// 시간에 따라 쌓이는 선 그래프. height로 세로 길이를 바꿀 수 있다. series: [{ name, color, points: [{ x, y }] }]
export function LineChart({ series, xMax, yMax, xLabel, title, height = H }) {
  const top = niceMax(yMax ?? Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.y))));
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const toX = (x) => PAD.left + scale(x, xMax, innerW);
  const toY = (y) => PAD.top + innerH - scale(y, top, innerH);

  return (
    <figure className="peak-chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={title}>
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line x1={PAD.left} x2={W - PAD.right} y1={toY(top * r)} y2={toY(top * r)} className="peak-grid" />
            <text x={PAD.left - 6} y={toY(top * r) + 4} className="peak-axis" textAnchor="end">
              {Math.round(top * r)}
            </text>
          </g>
        ))}
        <text x={W - PAD.right} y={height - 6} className="peak-axis" textAnchor="end">
          {xLabel}
        </text>
        {series.map((s) =>
          s.points.length > 1 ? (
            <polyline
              key={s.name}
              points={s.points.map((p) => `${toX(p.x)},${toY(p.y)}`).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
            />
          ) : null
        )}
      </svg>
      <div className="peak-legend">
        {series.map((s) => (
          <span key={s.name}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </figure>
  );
}

// 세 방식의 두 지표 막대. groups: [{ label, values: [{ name, value, color }] }], 값은 0~1 비율
export function BarChart({ groups, title }) {
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const groupW = innerW / groups.length;
  const barW = groupW / (groups[0].values.length + 1);

  return (
    <figure className="peak-chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + innerH * (1 - r)} y2={PAD.top + innerH * (1 - r)} className="peak-grid" />
            <text x={PAD.left - 6} y={PAD.top + innerH * (1 - r) + 4} className="peak-axis" textAnchor="end">
              {r * 100}%
            </text>
          </g>
        ))}
        {groups.map((g, gi) => (
          <g key={g.label}>
            {g.values.map((v, vi) => {
              const h = innerH * v.value;
              const x = PAD.left + gi * groupW + barW * (vi + 0.5);
              return (
                <g key={v.name}>
                  <rect x={x} y={PAD.top + innerH - h} width={barW * 0.9} height={h} fill={v.color} rx="2" />
                  <text x={x + barW * 0.45} y={PAD.top + innerH - h - 4} className="peak-value" textAnchor="middle">
                    {Math.round(v.value * 100)}
                  </text>
                </g>
              );
            })}
            <text x={PAD.left + gi * groupW + groupW / 2} y={H - 6} className="peak-axis" textAnchor="middle">
              {g.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="peak-legend">
        {groups[0].values.map((v) => (
          <span key={v.name}>
            <i style={{ background: v.color }} />
            {v.name}
          </span>
        ))}
      </div>
    </figure>
  );
}

// α 곡선: x = 확률 낮은 고객 이탈, y = 지킨 구매 고객. points: [{ x, y, label, highlight }]
export function TradeoffChart({ points, title }) {
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const xMax = 0.5;
  const toX = (x) => PAD.left + scale(Math.min(x, xMax), xMax, innerW);
  const toY = (y) => PAD.top + innerH - scale(y, 1, innerH);
  const curve = points.filter((p) => !p.fifo).sort((a, b) => a.x - b.x);

  return (
    <figure className="peak-chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line x1={PAD.left} x2={W - PAD.right} y1={toY(r)} y2={toY(r)} className="peak-grid" />
            <text x={PAD.left - 6} y={toY(r) + 4} className="peak-axis" textAnchor="end">
              {r * 100}%
            </text>
          </g>
        ))}
        {[0, 0.25, 0.5].map((x) => (
          <text key={x} x={toX(x)} y={H - 6} className="peak-axis" textAnchor="middle">
            {x * 100}%
          </text>
        ))}
        <polyline points={curve.map((p) => `${toX(p.x)},${toY(p.y)}`).join(" ")} fill="none" className="peak-curve" />
        {points.map((p) => (
          <g key={p.label}>
            <circle
              cx={toX(p.x)}
              cy={toY(p.y)}
              r={p.highlight || p.fifo ? 5 : 3}
              className={p.fifo ? "peak-dot-fifo" : p.highlight ? "peak-dot-chosen" : "peak-dot"}
            />
            {(p.highlight || p.fifo) && (
              <text x={toX(p.x) + 8} y={toY(p.y) + 4} className="peak-value">
                {p.label}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="peak-legend">
        <span>가로: 확률 낮은 고객 이탈 · 세로: 지킨 구매 고객 · 점: α</span>
      </div>
    </figure>
  );
}

