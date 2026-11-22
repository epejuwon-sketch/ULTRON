import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, Search, X } from "lucide-react";
import { ALL_PAGES, ModuleId, PageDef } from "../../catalog/navigation";
import { UltronLogo } from "../UltronLogo";

/* ==================== STATUS INDICATOR ==================== */
export type StatusTone = "success" | "info" | "warn" | "danger" | "neutral";

export function StatusIndicator({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: StatusTone;
}) {
  return (
    <span className={`status-indicator status-${tone}`}>
      <span className="status-dot" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

/* ==================== METRIC DISPLAY ==================== */
export function MetricDisplay({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: StatusTone;
}) {
  return (
    <div className="telemetry-cell">
      <div className="row-between">
        <span className="telemetry-label">{label}</span>
        {tone && <span className={`status-dot-only dot-${tone}`} aria-hidden="true" />}
      </div>
      <div className="telemetry-value mono">{value}</div>
      {sub && <div className="telemetry-sub">{sub}</div>}
    </div>
  );
}

/* ==================== PAGE HEADER ==================== */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div style={{ minWidth: 0 }}>
        {eyebrow && <div className="eyebrow-mono">{eyebrow}</div>}
        <h1 className="page-header-title">{title}</h1>
        <p className="page-header-desc">{description}</p>
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

/* ==================== SEARCH BAR & FILTER BAR ==================== */
export function SearchBar({
  id,
  value,
  onChange,
  placeholder = "Search...",
}: {
  id?: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-bar">
      <Search size={15} className="search-bar-icon" aria-hidden="true" />
      <input
        id={id}
        type="search"
        className="input search-bar-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
      />
      {value && (
        <button
          type="button"
          className="search-bar-clear"
          onClick={() => onChange("")}
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}

export function FilterBar<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div className="filter-bar" role="tablist">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={value === opt.value}
          className={`filter-chip ${value === opt.value ? "active" : ""}`}
          onClick={() => onChange(opt.value)}
        >
          <span>{opt.label}</span>
          {opt.count !== undefined && <span className="filter-count mono">{opt.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ==================== DATA TABLE ==================== */
export interface TableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  mono?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyTitle = "No records found",
  emptyDescription = "No data has been persisted for this view yet.",
}: {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={rowKey(r, idx)}>
              {columns.map((c) => (
                <td key={c.key} className={c.mono ? "mono" : undefined}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ==================== STATES (LOADING / EMPTY / ERROR) ==================== */
export function LoadingState({ label = "Synchronizing with ULTRON backend..." }: { label?: string }) {
  return (
    <div className="state-box">
      <UltronLogo variant="loader" size={38} subtitle={label} />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state-box">
      <UltronLogo variant="empty" size={38} />
      <div className="state-title">{title}</div>
      <p className="muted" style={{ margin: 0, maxWidth: 420 }}>{description}</p>
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Backend Request Failed",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="alert-box alert-error" role="alert">
      <div className="row-between">
        <div className="row">
          <AlertTriangle size={15} />
          <strong>{title}</strong>
        </div>
        {onRetry && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
      <div style={{ marginTop: 4 }}>{message}</div>
    </div>
  );
}

/* ==================== MODAL, DRAWER & CONFIRMATION DIALOG ==================== */
export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="row-between modal-header">
          <h3>{title}</h3>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop drawer-right-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="drawer-right-panel" onClick={(e) => e.stopPropagation()}>
        <div className="row-between modal-header">
          <h3>{title}</h3>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close panel">
            <X size={14} />
          </button>
        </div>
        <div className="drawer-right-body">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmationDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  destructive = true,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <p className="muted" style={{ marginTop: 0 }}>{message}</p>
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button
          type="button"
          className={destructive ? "btn btn-danger" : "btn"}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

/* ==================== TOAST SYSTEM ==================== */
interface ToastItem {
  id: number;
  tone: "info" | "success" | "error";
  message: string;
}

const ToastContext = createContext<{ pushToast: (message: string, tone?: "info" | "success" | "error") => void }>({
  pushToast: () => {},
});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const pushToast = useCallback((message: string, tone: "info" | "success" | "error" = "info") => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((prev) => [...prev.slice(-3), { id, tone, message }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 3600);
  }, []);

  return (
    <ToastContext.Provider value={{ pushToast }}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast-item toast-${t.tone}`}>
            {t.tone === "success" ? <CheckCircle2 size={15} /> : t.tone === "error" ? <AlertTriangle size={15} /> : <Info size={15} />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

/* ==================== ACTIVITY FEED & APPROVAL CARD ==================== */
export interface ActivityEntry {
  id: string;
  title: string;
  actor?: string;
  status?: string;
  timestamp?: string;
  detail?: string;
}

export function ActivityFeed({
  items,
  emptyLabel = "No recorded activity events yet.",
}: {
  items: ActivityEntry[];
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return <EmptyState title="No Activity" description={emptyLabel} />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((it) => (
        <div key={it.id} className="list-item">
          <div className="row-between">
            <strong>{it.title}</strong>
            {it.status && <span className="pill">{it.status}</span>}
          </div>
          {it.detail && <div className="muted">{it.detail}</div>}
          <div className="muted mono" style={{ fontSize: 11 }}>
            {it.actor || "system"} {it.timestamp ? `· ${it.timestamp}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ApprovalCard({
  approval,
  onApprove,
  onReject,
}: {
  approval: any;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const pending = approval.status === "PENDING";
  return (
    <div className="list-item">
      <div className="row-between">
        <strong>{approval.action_type || approval.resource || "Governance Action"}</strong>
        <div className="row">
          {approval.estimated_cost_usd !== undefined && (
            <span className="pill pill-warn">${approval.estimated_cost_usd}</span>
          )}
          <span className={`pill ${pending ? "pill-warn" : approval.status === "APPROVED" ? "pill-green" : "pill-danger"}`}>
            {approval.status}
          </span>
        </div>
      </div>
      <div className="muted">{approval.reason || approval.description || "Requires ApprovalGate review."}</div>
      <div className="muted mono" style={{ fontSize: 11 }}>{approval.approval_id}</div>
      {pending && (
        <div className="row" style={{ marginTop: 4 }}>
          <button type="button" className="btn btn-sm" onClick={() => onApprove(approval.approval_id)}>
            Approve
          </button>
          <button type="button" className="btn btn-danger btn-sm" onClick={() => onReject(approval.approval_id)}>
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

/* ==================== RESPONSIVE WORKSPACE ==================== */
export function ResponsiveWorkspace({
  subPages,
  activeSubPage,
  onSelectSubPage,
  children,
}: {
  subPages: PageDef[];
  activeSubPage: string;
  onSelectSubPage: (subId: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="workspace-container">
      {subPages.length > 1 && (
        <nav className="subpage-tabs" aria-label="Module sections">
          {subPages.map((p) => (
            <button
              key={p.id}
              id={`subtab-${p.module}-${p.id}`}
              type="button"
              className={`subpage-tab ${activeSubPage === p.id ? "active" : ""}`}
              onClick={() => onSelectSubPage(p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>
      )}
      <div className="workspace-body">{children}</div>
    </div>
  );
}

/* ==================== COMMAND PALETTE (Cmd/Ctrl+K) ==================== */
export function CommandPalette({
  open,
  onClose,
  onNavigate,
}: {
  open: boolean;
  onClose: () => void;
  onNavigate: (moduleId: ModuleId, subPageId: string) => void;
}) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  if (!open) return null;
  const q = query.trim().toLowerCase();
  const matches = ALL_PAGES.filter(
    (p) =>
      !q ||
      p.label.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q) ||
      p.module.toLowerCase().includes(q) ||
      p.keywords.some((k) => k.includes(q))
  ).slice(0, 18);

  return (
    <Modal open={open} title="ULTRON Command Palette (111+ Pages)" onClose={onClose}>
      <SearchBar
        id="command-palette-search"
        value={query}
        onChange={setQuery}
        placeholder="Jump to any page, subsystem, agent workspace, or setting..."
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12, maxHeight: 380, overflowY: "auto" }}>
        {matches.map((p) => (
          <button
            key={`${p.module}-${p.id}`}
            type="button"
            className="list-item list-item-btn"
            onClick={() => {
              onNavigate(p.module, p.id);
              onClose();
            }}
          >
            <div className="row-between" style={{ width: "100%" }}>
              <strong>{p.label}</strong>
              <span className="pill mono">{p.module.toUpperCase()}</span>
            </div>
            <div className="muted">{p.description}</div>
          </button>
        ))}
        {matches.length === 0 && <div className="muted">No matching ULTRON pages found.</div>}
      </div>
    </Modal>
  );
}
