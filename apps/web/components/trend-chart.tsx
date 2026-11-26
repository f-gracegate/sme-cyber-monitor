import { formatDate } from "@/lib/format";

/** Small, labelled line chart of the daily posture score (0–100). */
export function TrendChart({ points }: { points: { day: string; score: number }[] }) {
  if (points.length === 0) {
    return <p className="py-8 text-center text-sm text-muted">The trend appears after the first day of monitoring.</p>;
  }
  const w = 560;
  const h = 160;
  const pad = { l: 30, r: 10, t: 10, b: 24 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const x = (i: number) => pad.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  const y = (score: number) => pad.t + ih - (score / 100) * ih;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${pad.t + ih} L${x(0).toFixed(1)},${pad.t + ih} Z`;
  const last = points[points.length - 1];

  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full" role="img" aria-label={`Security posture score over time, currently ${last.score}`}>
        {[0, 50, 100].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={w - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeDasharray={v === 0 ? undefined : "3 4"} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fill="var(--text-subtle)">
              {v}
            </text>
          </g>
        ))}
        <path d={area} fill="var(--primary)" opacity="0.08" />
        <path d={line} fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={p.day} cx={x(i)} cy={y(p.score)} r={i === points.length - 1 ? 4 : 2.5} fill="var(--primary)">
            <title>{`${formatDate(`${p.day}T12:00:00`)}: ${p.score}`}</title>
          </circle>
        ))}
        <text x={x(0)} y={h - 6} fontSize="10" fill="var(--text-subtle)" textAnchor={points.length === 1 ? "middle" : "start"}>
          {formatDate(`${points[0].day}T12:00:00`)}
        </text>
        {points.length > 1 && (
          <text x={x(points.length - 1)} y={h - 6} fontSize="10" fill="var(--text-subtle)" textAnchor="end">
            {formatDate(`${last.day}T12:00:00`)}
          </text>
        )}
      </svg>
    </figure>
  );
}
