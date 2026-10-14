"use client";

import { useEffect, useId, useRef, useState } from "react";
import { searchAddressSuggestions, type Place } from "@/lib/place";
import styles from "./AddressSearchInput.module.css";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSelect: (place: Place) => void;
  ariaLabel: string;
  placeholder?: string;
  className?: string;
  containerClassName?: string;
  autoFocus?: boolean;
  required?: boolean;
};

export function AddressSearchInput({ value, onChange, onSelect, ariaLabel, placeholder, className, containerClassName, autoFocus, required }: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selectedLabel = useRef<string | null>(null);
  const [result, setResult] = useState<{ query: string; places: Place[] } | null>(null);
  const [open, setOpen] = useState(true);
  const [active, setActive] = useState(-1);
  const places = open && result?.query === value.trim() ? result.places : [];

  useEffect(() => {
    const query = value.trim();
    if (query.length < 2 || query === selectedLabel.current) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void searchAddressSuggestions(query)
        .then((found) => { if (!cancelled) setResult({ query, places: found }); })
        .catch(() => { if (!cancelled) setResult({ query, places: [] }); });
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [value]);

  function choose(place: Place) {
    selectedLabel.current = place.label;
    setOpen(false);
    setActive(-1);
    onSelect(place);
  }

  return (
    <div ref={rootRef} className={`${styles.root} ${containerClassName ?? ""}`} onBlur={(event) => {
      if (!rootRef.current?.contains(event.relatedTarget)) setOpen(false);
    }}>
      <input
        autoFocus={autoFocus}
        required={required}
        className={`${styles.input} ${className ?? ""}`}
        value={value}
        onChange={(event) => {
          selectedLabel.current = null;
          setResult(null);
          setActive(-1);
          setOpen(true);
          onChange(event.target.value);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && places.length) { event.preventDefault(); setActive((index) => (index + 1) % places.length); }
          if (event.key === "ArrowUp" && places.length) { event.preventDefault(); setActive((index) => (index + places.length - 1) % places.length); }
          if (event.key === "Enter" && active >= 0 && places[active]) { event.preventDefault(); choose(places[active]); }
          if (event.key === "Escape") { setOpen(false); setActive(-1); }
        }}
        placeholder={placeholder}
        aria-label={ariaLabel}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={places.length > 0}
        aria-controls={places.length ? listId : undefined}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
      />
      {places.length > 0 && (
        <div className={styles.list} id={listId} role="listbox" aria-label={`${ariaLabel} 후보`}>
          {places.map((place, index) => (
            <button
              key={`${place.label}-${place.lat}-${place.lng}`}
              id={`${listId}-${index}`}
              type="button"
              role="option"
              aria-selected={index === active}
              className={styles.option}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(place)}
            >{place.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
