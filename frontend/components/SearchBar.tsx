import { Command, Search, X } from "lucide-react";
import { FormEvent, RefObject } from "react";

type SearchBarProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  inputRef: RefObject<HTMLInputElement | null>;
  busy: boolean;
};

export function SearchBar({
  value,
  onChange,
  onSubmit,
  onClear,
  inputRef,
  busy,
}: SearchBarProps) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="search-shell" onSubmit={submit} role="search">
      <Search aria-hidden="true" size={19} strokeWidth={1.8} />
      <input
        ref={inputRef}
        aria-label="用自然语言搜索图片"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="试试“夕阳下奔跑的狗”或“穿红衣服的人”"
        autoComplete="off"
      />
      {value ? (
        <button className="clear-search" type="button" onClick={onClear} aria-label="清除搜索">
          <X size={16} />
        </button>
      ) : (
        <span className="command-hint" aria-hidden="true">
          <Command size={12} /> K
        </span>
      )}
      <button className="search-submit" type="submit" disabled={busy || !value.trim()}>
        {busy ? "搜索中" : "搜索"}
      </button>
    </form>
  );
}
