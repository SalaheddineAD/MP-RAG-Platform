type FieldProps = {
  label: string;
  hint?: string;
  children: React.ReactNode;
};

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="flex flex-col gap-2">
      <span className="font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
        {label}
      </span>
      {children}
      {hint ? <span className="text-xs text-ink-muted">{hint}</span> : null}
    </label>
  );
}

export const controlClass =
  "w-full rounded-none border border-line bg-bg-elevated px-3 py-2.5 text-sm text-ink outline-none transition focus:border-accent";

export const checkboxRowClass =
  "flex items-center gap-2 text-sm text-ink-muted";
