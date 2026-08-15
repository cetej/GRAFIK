import { useState, type ReactNode } from 'react';

interface SectionProps {
  title: string;
  badge?: string | number;
  /** @default true */
  defaultOpen?: boolean;
  /** When set, the open/closed state persists to localStorage under `grafik.section.<storageKey>`
   * and is restored from there on mount (overriding defaultOpen once a value was ever stored). */
  storageKey?: string;
  /** Fired only on a closed→open transition (never on mount, never on close) — e.g. to lazily
   * refresh data the first time a user actually looks at a section. */
  onOpen?: () => void;
  /** Extra controls rendered in the header (e.g. a small action button); clicks inside it never
   * toggle the section. */
  headerExtra?: ReactNode;
  children?: ReactNode;
}

function storageKeyFor(key: string): string {
  return `grafik.section.${key}`;
}

/** Collapsible sidebar/panel card used across the editor (M6-UX1) — replaces the old flat
 * `.editor-section` blocks with a visually distinct, collapsible, badge-capable header. */
export default function Section(props: SectionProps) {
  const { title, badge, defaultOpen = true, storageKey, onOpen, headerExtra, children } = props;
  const [open, setOpen] = useState(() => {
    if (storageKey) {
      const stored = localStorage.getItem(storageKeyFor(storageKey));
      if (stored !== null) return stored === '1';
    }
    return defaultOpen;
  });

  function toggle() {
    const next = !open;
    setOpen(next);
    if (storageKey) localStorage.setItem(storageKeyFor(storageKey), next ? '1' : '0');
    if (next) onOpen?.();
  }

  return (
    <div className="section-card">
      <div
        className="section-header"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle();
          }
        }}
      >
        <span className="section-arrow" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className="section-title">{title}</span>
        {badge !== undefined && badge !== null && badge !== '' && <span className="section-badge">{badge}</span>}
        {headerExtra && (
          <span className="section-header-extra" onClick={(e) => e.stopPropagation()}>
            {headerExtra}
          </span>
        )}
      </div>
      {open && <div className="section-body">{children}</div>}
    </div>
  );
}
