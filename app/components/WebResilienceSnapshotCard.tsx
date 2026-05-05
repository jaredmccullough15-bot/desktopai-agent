"use client";

import { useState } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

export type PageStateSnapshot = {
  url?: string | null;
  title?: string | null;
  important_buttons?: string[] | null;
  important_inputs?: string[] | null;
  [key: string]: unknown;
};

export interface WebResilienceSnapshotCardProps {
  pageStateSnapshot?: PageStateSnapshot | null;
  detectedModals?: string[] | null;
  detectedOverlays?: string[] | null;
  failedAction?: string | null;
  attemptedFallbacks?: string[] | null;
  /** Show a skeleton loader while data is loading */
  loading?: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function hasWebResilienceData(props: WebResilienceSnapshotCardProps): boolean {
  const { pageStateSnapshot, detectedModals, detectedOverlays, failedAction, attemptedFallbacks } = props;
  return !!(
    (pageStateSnapshot && Object.keys(pageStateSnapshot).length > 0) ||
    (detectedModals && detectedModals.length > 0) ||
    (detectedOverlays && detectedOverlays.length > 0) ||
    failedAction ||
    (attemptedFallbacks && attemptedFallbacks.length > 0)
  );
}

function buildGuidance(props: WebResilienceSnapshotCardProps): string | null {
  const { detectedModals, detectedOverlays, failedAction } = props;

  if (detectedModals && detectedModals.length > 0) {
    return "Close or dismiss the popup, then retry.";
  }
  if (detectedOverlays && detectedOverlays.length > 0) {
    return "Something is blocking the page. Clear it, then retry.";
  }
  if (failedAction && failedAction.toLowerCase().includes("click")) {
    return "Bill could not click the expected control. Check if the button moved or changed.";
  }
  return null;
}

function formatFallbackName(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Sub-components ───────────────────────────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
      {children}
    </p>
  );
}

function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: "default" | "amber" | "rose" }) {
  const classes =
    variant === "amber"
      ? "rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300"
      : variant === "rose"
      ? "rounded border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[11px] text-rose-300"
      : "rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300";
  return <span className={classes}>{children}</span>;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function WebResilienceSnapshotCard(props: WebResilienceSnapshotCardProps) {
  const {
    pageStateSnapshot,
    detectedModals,
    detectedOverlays,
    failedAction,
    attemptedFallbacks,
    loading,
  } = props;

  const [showRaw, setShowRaw] = useState(false);

  // Loading state
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
          <span className="text-xs text-slate-500">Loading page snapshot…</span>
        </div>
      </div>
    );
  }

  const hasData = hasWebResilienceData(props);
  const guidance = hasData ? buildGuidance(props) : null;

  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 px-4 py-4">
      {/* Title row */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-base">⚠️</span>
        <h3 className="text-sm font-semibold text-slate-100">Why Bill got stuck</h3>
        {!hasData && (
          <span className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">
            No snapshot
          </span>
        )}
      </div>

      {/* No data fallback */}
      {!hasData && (
        <p className="text-xs text-slate-500">
          Bill did not capture enough page detail for this failure.
        </p>
      )}

      {hasData && (
        <div className="flex flex-col gap-4">

          {/* 1. Page Bill was on */}
          {(pageStateSnapshot?.url || pageStateSnapshot?.title) && (
            <div>
              <SectionHeader>Page Bill was on</SectionHeader>
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 space-y-1">
                {pageStateSnapshot?.title && (
                  <p className="text-xs font-medium text-slate-200">{pageStateSnapshot.title}</p>
                )}
                {pageStateSnapshot?.url && (
                  <p
                    className="truncate text-[11px] text-slate-400 font-mono"
                    title={pageStateSnapshot.url}
                  >
                    {pageStateSnapshot.url}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* 2. What Bill saw */}
          {((detectedModals && detectedModals.length > 0) ||
            (detectedOverlays && detectedOverlays.length > 0) ||
            (pageStateSnapshot?.important_buttons && pageStateSnapshot.important_buttons.length > 0) ||
            (pageStateSnapshot?.important_inputs && pageStateSnapshot.important_inputs.length > 0)) && (
            <div>
              <SectionHeader>What Bill saw</SectionHeader>
              <div className="flex flex-col gap-2">
                {detectedModals && detectedModals.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-slate-500">Popups / modals</p>
                    <div className="flex flex-wrap gap-1">
                      {detectedModals.map((m, i) => (
                        <Badge key={`modal-${i}`} variant="rose">
                          {m}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {detectedOverlays && detectedOverlays.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-slate-500">Overlays blocking the page</p>
                    <div className="flex flex-wrap gap-1">
                      {detectedOverlays.map((o, i) => (
                        <Badge key={`overlay-${i}`} variant="amber">
                          {o}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {pageStateSnapshot?.important_buttons && pageStateSnapshot.important_buttons.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-slate-500">Buttons visible</p>
                    <div className="flex flex-wrap gap-1">
                      {pageStateSnapshot.important_buttons.map((b, i) => (
                        <Badge key={`btn-${i}`}>{b}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {pageStateSnapshot?.important_inputs && pageStateSnapshot.important_inputs.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-slate-500">Inputs visible</p>
                    <div className="flex flex-wrap gap-1">
                      {pageStateSnapshot.important_inputs.map((inp, i) => (
                        <Badge key={`inp-${i}`}>{inp}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. What failed */}
          {failedAction && (
            <div>
              <SectionHeader>What failed</SectionHeader>
              <div className="flex items-center gap-2">
                <span className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-xs font-mono text-rose-300">
                  {failedAction}
                </span>
              </div>
            </div>
          )}

          {/* 4. What Bill tried */}
          {attemptedFallbacks && attemptedFallbacks.length > 0 && (
            <div>
              <SectionHeader>What Bill tried</SectionHeader>
              <ol className="flex flex-col gap-1">
                {attemptedFallbacks.map((fb, i) => (
                  <li key={`fb-${i}`} className="flex items-center gap-2 text-xs text-slate-300">
                    <span className="shrink-0 rounded-full bg-slate-700 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">
                      {i + 1}
                    </span>
                    <span>{formatFallbackName(fb)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* 5. What to do next */}
          <div>
            <SectionHeader>What to do next</SectionHeader>
            <div className="rounded-lg border border-violet-500/20 bg-violet-500/10 px-3 py-2">
              <p className="text-xs leading-relaxed text-violet-200">
                {guidance ?? "Review the details above and select a recovery action below."}
              </p>
            </div>
          </div>

          {/* Collapsible raw snapshot */}
          <div>
            <button
              onClick={() => setShowRaw((v) => !v)}
              className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600 hover:text-slate-400 transition-colors"
            >
              <span>{showRaw ? "▾" : "▸"}</span>
              <span>Technical details</span>
            </button>
            {showRaw && (
              <pre className="mt-2 max-h-52 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-[10px] leading-relaxed text-slate-400">
                {JSON.stringify(
                  {
                    page_state_snapshot: pageStateSnapshot,
                    detected_modals: detectedModals,
                    detected_overlays: detectedOverlays,
                    failed_action: failedAction,
                    attempted_fallbacks: attemptedFallbacks,
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
