"use client";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="rounded-md border border-line bg-surface p-6">
      <h1 className="text-lg">Something went wrong</h1>
      <p className="mt-2 text-sm text-muted">{error.message}</p>
      <button type="button" onClick={reset} className="mt-4 rounded-md border border-line px-3 py-2 text-sm">
        Try again
      </button>
    </div>
  );
}
