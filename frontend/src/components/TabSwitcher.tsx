interface TabSwitcherProps<T extends string> {
  tabs: { id: T; label: string }[];
  active: T;
  onChange: (tab: T) => void;
}

// PROMPT_3's segmented-control pattern: rounded-full lavender track,
// active tab in white with a subtle shadow — understated, not bold-filled.
export default function TabSwitcher<T extends string>({ tabs, active, onChange }: TabSwitcherProps<T>) {
  return (
    <div className="flex rounded-full bg-white/10 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`flex-1 rounded-full py-1.5 text-sm font-bold transition ${
            active === tab.id ? "bg-white text-fpl-black shadow-sm" : "text-white/60"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
