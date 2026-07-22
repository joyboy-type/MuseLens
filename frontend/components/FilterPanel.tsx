import type {
  DatePreset,
  ImageOrientation,
  SearchFilters,
  SearchSort,
  ImageTag,
} from "@/lib/types";
import { activeFilterCount, EMPTY_FILTERS } from "@/lib/search-filters";
import { Check, Filter, RotateCcw, SlidersHorizontal, X } from "lucide-react";

type FilterPanelProps = {
  open: boolean;
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  onApply: () => void;
  onClose: () => void;
  availableTags: ImageTag[];
};

const FORMATS = [
  ["image/jpeg", "JPEG"],
  ["image/png", "PNG"],
  ["image/webp", "WebP"],
] as const;

const ORIENTATIONS: [ImageOrientation, string][] = [
  ["landscape", "横图"],
  ["portrait", "竖图"],
  ["square", "方图"],
];

const DATES: [DatePreset, string][] = [
  ["all", "不限"],
  ["week", "近 7 天"],
  ["month", "近 30 天"],
  ["year", "近一年"],
];

const SORTS: [SearchSort, string][] = [
  ["relevance", "相关度"],
  ["newest", "最新导入"],
  ["oldest", "最早导入"],
  ["size_desc", "文件最大"],
];

function toggle<T>(items: T[], item: T): T[] {
  return items.includes(item) ? items.filter((value) => value !== item) : [...items, item];
}

export function FilterPanel({
  open,
  filters,
  onChange,
  onApply,
  onClose,
  availableTags,
}: FilterPanelProps) {
  if (!open) return null;

  return (
    <div className="filter-scrim" onMouseDown={onClose}>
      <section
        className="filter-panel"
        aria-label="组合筛选"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="filter-heading">
          <div>
            <span><SlidersHorizontal size={15} /> 组合筛选</span>
            <small>语义搜索和图片属性会共同参与检索</small>
          </div>
          <button onClick={onClose} aria-label="关闭筛选"><X size={17} /></button>
        </div>

        <div className="filter-grid">
          <fieldset>
            <legend>文件格式</legend>
            <div className="option-group">
              {FORMATS.map(([value, label]) => {
                const selected = filters.contentTypes.includes(value);
                return (
                  <button
                    className={selected ? "selected" : ""}
                    key={value}
                    onClick={() => onChange({
                      ...filters,
                      contentTypes: toggle(filters.contentTypes, value),
                    })}
                    type="button"
                  >
                    {selected && <Check size={12} />} {label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend>画面方向</legend>
            <div className="option-group orientation-options">
              {ORIENTATIONS.map(([value, label]) => {
                const selected = filters.orientations.includes(value);
                return (
                  <button
                    className={selected ? "selected" : ""}
                    key={value}
                    onClick={() => onChange({
                      ...filters,
                      orientations: toggle(filters.orientations, value),
                    })}
                    type="button"
                  >
                    <i className={`orientation-icon ${value}`} /> {label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          {availableTags.length > 0 && (
            <fieldset className="tag-fieldset">
              <legend>AI 自动标签</legend>
              <div className="option-group tag-options">
                {availableTags.map((tag) => {
                  const selected = filters.tags.includes(tag.slug);
                  return (
                    <button
                      className={selected ? "selected" : ""}
                      key={tag.slug}
                      onClick={() => onChange({
                        ...filters,
                        tags: toggle(filters.tags, tag.slug),
                      })}
                      title={`SigLIP2 自动标签：${tag.label}`}
                      type="button"
                    >
                      {selected && <Check size={12} />} {tag.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          )}

          <fieldset>
            <legend>导入时间</legend>
            <div className="segmented-options">
              {DATES.map(([value, label]) => (
                <button
                  className={filters.datePreset === value ? "selected" : ""}
                  key={value}
                  onClick={() => onChange({ ...filters, datePreset: value })}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>图片规格</legend>
            <div className="select-row">
              <label>
                最小宽度
                <select
                  value={filters.minWidth ?? ""}
                  onChange={(event) => onChange({
                    ...filters,
                    minWidth: event.target.value ? Number(event.target.value) : null,
                  })}
                >
                  <option value="">不限</option>
                  <option value="1280">1280 px</option>
                  <option value="1920">1920 px</option>
                  <option value="3840">3840 px</option>
                </select>
              </label>
              <label>
                最大文件
                <select
                  value={filters.maxSizeMB ?? ""}
                  onChange={(event) => onChange({
                    ...filters,
                    maxSizeMB: event.target.value ? Number(event.target.value) : null,
                  })}
                >
                  <option value="">不限</option>
                  <option value="1">1 MB</option>
                  <option value="5">5 MB</option>
                  <option value="10">10 MB</option>
                </select>
              </label>
            </div>
          </fieldset>

          <fieldset className="sort-fieldset">
            <legend>结果排序</legend>
            <div className="sort-options">
              {SORTS.map(([value, label]) => (
                <label key={value}>
                  <input
                    checked={filters.sort === value}
                    name="result-sort"
                    onChange={() => onChange({ ...filters, sort: value })}
                    type="radio"
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <footer className="filter-actions">
          <button
            className="reset-filters"
            disabled={activeFilterCount(filters) === 0}
            onClick={() => onChange(EMPTY_FILTERS)}
            type="button"
          >
            <RotateCcw size={14} /> 重置
          </button>
          <button className="apply-filters" onClick={onApply} type="button">
            <Filter size={14} /> 应用筛选
          </button>
        </footer>
      </section>
    </div>
  );
}
