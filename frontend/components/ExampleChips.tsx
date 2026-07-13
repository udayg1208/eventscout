"use client";

const EXAMPLES = [
  "AI workshops in Bangalore this weekend",
  "Hackathons happening next month",
  "Free machine learning webinars",
  "Startup events in Mumbai",
  "Tech conferences in Hyderabad",
];

export function ExampleChips({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {EXAMPLES.map((example) => (
        <button
          key={example}
          type="button"
          onClick={() => onPick(example)}
          className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm text-slate-600 transition hover:border-violet-300 hover:text-violet-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/40 dark:hover:text-violet-300"
        >
          {example}
        </button>
      ))}
    </div>
  );
}
