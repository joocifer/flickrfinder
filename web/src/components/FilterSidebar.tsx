import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type FilterState } from "../api";

type ExifOp = "=" | "!=" | "~=" | "<" | "<=" | ">" | ">=";
const EXIF_OPS: { op: ExifOp; label: string; title: string }[] = [
  { op: "=", label: "=", title: "equal (case-insensitive)" },
  { op: "!=", label: "≠", title: "not equal" },
  { op: "~=", label: "~=", title: "substring contains (case-insensitive)" },
  { op: "<", label: "<", title: "less than (numeric)" },
  { op: "<=", label: "≤", title: "less than or equal (numeric)" },
  { op: ">", label: ">", title: "greater than (numeric)" },
  { op: ">=", label: "≥", title: "greater than or equal (numeric)" },
];

type Props = {
  filters: FilterState;
  onChange: (updater: (prev: FilterState) => FilterState) => void;
};

export function FilterSidebar({ filters, onChange }: Props) {
  return (
    <aside className="w-full lg:w-72 lg:shrink-0 lg:max-h-[calc(100vh-4rem)] lg:overflow-y-auto lg:pr-2 space-y-5">
      <Section title="Camera / Lens">
        <Field label="Camera">
          <TextInput
            value={filters.camera}
            placeholder="e.g. X-T5, K20D, Nikon"
            onChange={(v) => onChange((f) => ({ ...f, camera: v, offset: 0 }))}
          />
        </Field>
        <Field label="Lens">
          <TextInput
            value={filters.lens}
            placeholder="e.g. 50mm, XF23"
            onChange={(v) => onChange((f) => ({ ...f, lens: v, offset: 0 }))}
          />
        </Field>
      </Section>

      <RangeSection
        title="Focal length (mm)"
        min={filters.focal_min}
        max={filters.focal_max}
        onMin={(v) => onChange((f) => ({ ...f, focal_min: v, offset: 0 }))}
        onMax={(v) => onChange((f) => ({ ...f, focal_max: v, offset: 0 }))}
      />
      <RangeSection
        title="Aperture (f-number)"
        min={filters.aperture_min}
        max={filters.aperture_max}
        onMin={(v) => onChange((f) => ({ ...f, aperture_min: v, offset: 0 }))}
        onMax={(v) => onChange((f) => ({ ...f, aperture_max: v, offset: 0 }))}
      />
      <RangeSection
        title="ISO"
        min={filters.iso_min}
        max={filters.iso_max}
        onMin={(v) => onChange((f) => ({ ...f, iso_min: v, offset: 0 }))}
        onMax={(v) => onChange((f) => ({ ...f, iso_max: v, offset: 0 }))}
      />

      <Section title="Shutter (seconds)">
        <Field label="Faster than">
          <TextInput
            value={filters.shutter_faster_than}
            placeholder="0.004 = 1/250"
            onChange={(v) => onChange((f) => ({ ...f, shutter_faster_than: v, offset: 0 }))}
          />
        </Field>
        <Field label="Slower than">
          <TextInput
            value={filters.shutter_slower_than}
            placeholder="1"
            onChange={(v) => onChange((f) => ({ ...f, shutter_slower_than: v, offset: 0 }))}
          />
        </Field>
      </Section>

      <Section title="Date taken">
        <Field label="From">
          <TextInput
            value={filters.taken_after}
            placeholder="YYYY-MM-DD"
            onChange={(v) => onChange((f) => ({ ...f, taken_after: v, offset: 0 }))}
          />
        </Field>
        <Field label="To">
          <TextInput
            value={filters.taken_before}
            placeholder="YYYY-MM-DD"
            onChange={(v) => onChange((f) => ({ ...f, taken_before: v, offset: 0 }))}
          />
        </Field>
      </Section>

      <Section title="Tags (AND)">
        <ChipList
          items={filters.tag}
          onAdd={(v) => onChange((f) => ({ ...f, tag: [...f.tag, v], offset: 0 }))}
          onRemove={(i) =>
            onChange((f) => ({ ...f, tag: f.tag.filter((_, idx) => idx !== i), offset: 0 }))
          }
          placeholder="add a tag"
        />
      </Section>

      <Section title="EXIF (advanced)">
        <ExifFilter filters={filters} onChange={onChange} />
        <p className="mt-1 text-xs text-zinc-500">
          Operators: = ≠ ~= (substring) &lt; ≤ &gt; ≥
        </p>
      </Section>

      <Section title="Visibility">
        <div className="flex gap-2">
          {(["", "public", "private"] as const).map((v) => (
            <button
              key={v || "any"}
              onClick={() => onChange((f) => ({ ...f, public: v, offset: 0 }))}
              className={`px-3 py-1 rounded text-sm border transition-colors ${
                filters.public === v
                  ? "bg-amber-400 text-zinc-950 border-amber-400"
                  : "border-zinc-700 hover:border-zinc-500"
              }`}
            >
              {v || "any"}
            </button>
          ))}
        </div>
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function RangeSection({
  title,
  min,
  max,
  onMin,
  onMax,
}: {
  title: string;
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
}) {
  return (
    <Section title={title}>
      <div className="grid grid-cols-2 gap-2">
        <TextInput placeholder="min" value={min} onChange={onMin} />
        <TextInput placeholder="max" value={max} onChange={onMax} />
      </div>
    </Section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block mb-1 text-xs text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm placeholder:text-zinc-600 focus:border-amber-400 focus:outline-none"
    />
  );
}

function ChipList({
  items,
  onAdd,
  onRemove,
  placeholder,
}: {
  items: string[];
  onAdd: (v: string) => void;
  onRemove: (i: number) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  // Reset draft when items shrink to 0 (e.g. after "clear all")
  useEffect(() => {
    if (items.length === 0) setDraft("");
  }, [items.length]);

  return (
    <>
      <div className="flex flex-wrap gap-1">
        {items.map((t, i) => (
          <span
            key={`${t}-${i}`}
            className="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
          >
            {t}
            <button
              onClick={() => onRemove(i)}
              className="text-zinc-400 hover:text-zinc-100"
              aria-label="remove"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const v = draft.trim();
          if (!v) return;
          onAdd(v);
          setDraft("");
        }}
      >
        <input
          type="text"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm placeholder:text-zinc-600 focus:border-amber-400 focus:outline-none"
        />
      </form>
    </>
  );
}

function ExifFilter({
  filters,
  onChange,
}: {
  filters: FilterState;
  onChange: (updater: (prev: FilterState) => FilterState) => void;
}) {
  const [tag, setTag] = useState("");
  const [op, setOp] = useState<ExifOp>("=");
  const [value, setValue] = useState("");

  const knownTags = useQuery({
    queryKey: ["exif-tags"],
    queryFn: api.exifTags,
    staleTime: 5 * 60_000,
  });

  const add = () => {
    const t = tag.trim();
    const v = value.trim();
    if (!t || !v) return;
    onChange((f) => ({ ...f, exif: [...f.exif, `${t}${op}${v}`], offset: 0 }));
    setTag("");
    setValue("");
  };

  return (
    <>
      <div className="flex flex-wrap gap-1">
        {filters.exif.map((chip, i) => (
          <span
            key={`${chip}-${i}`}
            className="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
          >
            {chip}
            <button
              onClick={() =>
                onChange((f) => ({
                  ...f,
                  exif: f.exif.filter((_, idx) => idx !== i),
                  offset: 0,
                }))
              }
              className="text-zinc-400 hover:text-zinc-100"
              aria-label="remove"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
        className="mt-1 space-y-1"
      >
        <input
          type="text"
          list="exif-tag-list"
          value={tag}
          placeholder={
            knownTags.data
              ? `tag (${knownTags.data.length} available)`
              : "tag, e.g. WhiteBalance"
          }
          onChange={(e) => setTag(e.target.value)}
          className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm placeholder:text-zinc-600 focus:border-amber-400 focus:outline-none"
        />
        <datalist id="exif-tag-list">
          {knownTags.data?.map((t) => (
            <option key={t.tag} value={t.tag} />
          ))}
        </datalist>
        <div className="flex gap-1">
          <select
            value={op}
            onChange={(e) => setOp(e.target.value as ExifOp)}
            title="Operator"
            className="rounded border border-zinc-800 bg-zinc-900 px-1 py-1.5 text-sm focus:border-amber-400 focus:outline-none"
          >
            {EXIF_OPS.map(({ op: o, label, title }) => (
              <option key={o} value={o} title={title}>
                {label}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={value}
            placeholder="value"
            onChange={(e) => setValue(e.target.value)}
            className="flex-1 rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm placeholder:text-zinc-600 focus:border-amber-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!tag.trim() || !value.trim()}
            className="rounded border border-zinc-800 px-3 py-1.5 text-sm hover:border-amber-400 hover:text-amber-400 disabled:opacity-30 disabled:hover:border-zinc-800 disabled:hover:text-zinc-100"
            title="Add EXIF filter"
          >
            +
          </button>
        </div>
      </form>
    </>
  );
}
