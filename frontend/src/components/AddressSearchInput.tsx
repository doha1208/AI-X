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
  inlineResults?: boolean;
};

export function AddressSearchInput({ value, onChange, onSelect, ariaLabel, placeholder, className, containerClassName, autoFocus, required, inlineResults = false }: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [editedValue, setEditedValue] = useState<string | null>(null);
  const [result, setResult] = useState<{ query: string; places: Place[] } | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const places = open && editedValue === value && result?.query === value.trim() ? result.places : [];

  useEffect(() => {
    const query = value.trim();
    if (!open || editedValue !== value || query.length < 2) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void searchAddressSuggestions(query)
        .then((found) => { if (!cancelled) setResult({ query, places: found }); })
        .catch(() => { if (!cancelled) setResult({ query, places: [] }); });
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [value, editedValue, open]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function choose(place: Place) {
    setEditedValue(null);
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
        autoComplete="off"
        className={`${styles.input} ${className ?? ""}`}
        value={value}
        onChange={(event) => {
          setEditedValue(event.target.value);
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
        <div className={`${styles.list} ${inlineResults ? styles.listInline : ""}`}>
          <div className={styles.listHeading} aria-hidden="true">검색 결과</div>
          <div id={listId} role="listbox" aria-label={`${ariaLabel} 후보`}>
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
        </div>
      )}
    </div>
  );
}
