import { ClipboardPaste, Link2 } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
  disabled?: boolean;
}

export function UrlInput({ value, onChange, error, disabled }: Props) {
  const canPaste = typeof navigator !== "undefined" && !!navigator.clipboard?.readText;

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) onChange(text.trim());
    } catch {
      /* permission denied: user can still paste manually */
    }
  };

  return (
    <div>
      <label htmlFor="url" className="sr-only">
        YouTube video link
      </label>
      <div
        className={`flex items-center gap-2 rounded-2xl border bg-ink-900 px-4 py-2 transition-colors focus-within:border-brand-400 ${
          error ? "border-brand-500" : "border-ink-700"
        }`}
      >
        <Link2 className="size-5 shrink-0 text-ink-400" aria-hidden />
        <input
          id="url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="Paste a YouTube link, e.g. https://youtu.be/…"
          className="min-w-0 flex-1 bg-transparent py-2 text-base text-ink-100 placeholder:text-ink-400 focus:outline-none"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "url-error" : undefined}
        />
        {canPaste && !value && (
          <button
            type="button"
            onClick={paste}
            disabled={disabled}
            className="btn-ghost px-3 py-1.5 text-xs"
          >
            <ClipboardPaste className="size-4" aria-hidden />
            Paste
          </button>
        )}
      </div>
      {error && (
        <p id="url-error" role="alert" className="mt-2 text-sm text-brand-400">
          {error}
        </p>
      )}
    </div>
  );
}
