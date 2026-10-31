import type { ReactNode } from "react";

export function Card({
  title,
  sub,
  children,
  note,
  takeaway,
  wide,
}: {
  wide?: boolean;
  title: string;
  sub?: ReactNode;
  children: ReactNode;
  note?: ReactNode;
  takeaway?: ReactNode;
}) {
  return (
    <div className={wide ? "card wide" : "card"}>
      <h3>{title}</h3>
      {sub && <p className="sub">{sub}</p>}
      {children}
      {takeaway && <p className="takeaway">{takeaway}</p>}
      {note && <p className="note">{note}</p>}
    </div>
  );
}

export type Col<R> = { key: string; label: string; num?: boolean; get: (r: R) => ReactNode };

export function TableView<R>({
  rows,
  cols,
  summary = "Show the numbers",
  open,
}: {
  rows: R[];
  cols: Col<R>[];
  summary?: string;
  open?: boolean;
}) {
  return (
    <details className="table-view" open={open}>
      <summary>{summary}</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c.key} className={c.num ? "num" : undefined}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c.key} className={c.num ? "num" : undefined}>
                    {c.get(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export type Status = "good" | "warning" | "critical";
const STATUS_COLOR: Record<Status, string> = { good: "var(--good)", warning: "var(--warning)", critical: "var(--critical)" };
const STATUS_ICON: Record<Status, string> = { good: "✓", warning: "!", critical: "✕" };

export function StatusTag({ status, children }: { status: Status; children: ReactNode }) {
  return (
    <span className="status">
      <i style={{ background: STATUS_COLOR[status] }} aria-hidden />
      <span aria-hidden>{STATUS_ICON[status]}</span>
      {children}
    </span>
  );
}

export function Tile({
  label,
  value,
  detail,
  status,
  statusText,
  meter,
}: {
  label: string;
  value: string;
  detail?: ReactNode;
  status?: Status;
  statusText?: string;
  meter?: number;
}) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {detail && <div className="detail">{detail}</div>}
      {meter != null && (
        <div className="meter" aria-hidden>
          <div style={{ width: `${Math.max(0, Math.min(100, meter))}%` }} />
        </div>
      )}
      {status && statusText && <StatusTag status={status}>{statusText}</StatusTag>}
    </div>
  );
}
