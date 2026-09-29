"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { reverseGeocode, type LatLng } from "@/lib/kakao";
import { LocateIcon, MinusIcon, PlusIcon } from "@/components/icons";
import styles from "./MapOverlays.module.css";

type ControlsProps = {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onLocate?: () => void;
  children?: ReactNode;
  className?: string;
};

export function MapControls({ onZoomIn, onZoomOut, onLocate, children, className = "" }: ControlsProps) {
  return (
    <div className={`${styles.controls} ${className}`}>
      {children}
      <button type="button" className={styles.controlButton} onClick={onZoomIn} aria-label="지도 확대">
        <PlusIcon size={20} />
      </button>
      <button type="button" className={styles.controlButton} onClick={onZoomOut} aria-label="지도 축소">
        <MinusIcon size={20} />
      </button>
      {onLocate && (
        <button
          type="button"
          className={`${styles.controlButton} ${styles.controlPrimary}`}
          onClick={onLocate}
          aria-label="내 위치로 이동"
        >
          <LocateIcon size={20} />
        </button>
      )}
    </div>
  );
}

export type LegendItem = { label: string; swatch: "line" | "dash" | "dot"; color: string };

export function MapLegend({ title, items, className = "" }: { title: string; items: LegendItem[]; className?: string }) {
  return (
    <div className={`${styles.legend} ${className}`}>
      <p className={styles.legendTitle}>{title}</p>
      <ul className={styles.legendList}>
        {items.map((item) => (
          <li key={item.label} className={styles.legendItem}>
            <span className={styles[item.swatch]} style={{ "--swatch": item.color } as React.CSSProperties} />
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export type MapPlace = LatLng & { label: string };
type MenuState = (LatLng & { x: number; y: number; address: string | null; loading: boolean }) | null;
export type MapMenuItem = { label: string; onSelect: (place: MapPlace) => void };

// 지도 우클릭 위치의 주소를 찾아 메뉴를 띄우고, 바깥 클릭·Esc로 닫는다.
export function useMapContextMenu() {
  const [menu, setMenu] = useState<MenuState>(null);
  const close = useCallback(() => setMenu(null), []);

  const open = useCallback(async (info: LatLng & { x: number; y: number }) => {
    setMenu({ ...info, address: null, loading: true });
    const address = await reverseGeocode(info.lat, info.lng);
    setMenu((m) => (m && m.x === info.x && m.y === info.y ? { ...m, address, loading: false } : m));
  }, []);

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    // 메뉴를 연 그 클릭이 바로 닫지 않도록 다음 틱부터 듣는다.
    const id = window.setTimeout(() => window.addEventListener("click", close), 0);
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu, close]);

  return { menu, open, close };
}

type PendingPick = (LatLng & { label: string | null }) | null;

// 지도 클릭 한 번으로 바로 확정하지 않고, 고른 지점을 표시해 둔 뒤 확인을 받는다. 다시 누르면 지점만 옮긴다.
export function usePendingPick() {
  const [pending, setPending] = useState<PendingPick>(null);
  const clear = useCallback(() => setPending(null), []);

  const pick = useCallback(async (latlng: LatLng) => {
    setPending({ ...latlng, label: null });
    const address = await reverseGeocode(latlng.lat, latlng.lng);
    const label = address ?? `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
    setPending((p) => (p && p.lat === latlng.lat && p.lng === latlng.lng ? { ...p, label } : p));
  }, []);

  return { pending, pick, clear };
}

type PickConfirmProps = {
  pending: PendingPick;
  confirmLabel: string;
  onConfirm: (place: MapPlace) => void;
  onCancel: () => void;
  className?: string;
};

export function PickConfirm({ pending, confirmLabel, onConfirm, onCancel, className = "" }: PickConfirmProps) {
  if (!pending) return null;
  const { label } = pending;
  return (
    <section className={`${styles.pickConfirm} ${className}`} aria-label="지도에서 고른 위치" aria-live="polite">
      <p className={styles.pickTitle}>선택한 위치</p>
      <p className={styles.pickAddress}>{label ?? "주소를 찾는 중..."}</p>
      <p className={styles.pickSub}>다른 곳을 누르면 위치를 바꿀 수 있어요</p>
      <div className={styles.pickActions}>
        <button type="button" className={styles.pickSecondary} onClick={onCancel}>
          취소
        </button>
        <button
          type="button"
          className={styles.pickPrimary}
          disabled={label === null}
          onClick={() => label !== null && onConfirm({ lat: pending.lat, lng: pending.lng, label })}
        >
          {confirmLabel}
        </button>
      </div>
    </section>
  );
}

export function MapContextMenu({ menu, items, onClose }: { menu: MenuState; items: MapMenuItem[]; onClose: () => void }) {
  if (!menu) return null;
  const label = menu.address ?? `${menu.lat.toFixed(5)}, ${menu.lng.toFixed(5)}`;
  const place: MapPlace = { lat: menu.lat, lng: menu.lng, label };
  return (
    <div
      className={styles.menu}
      role="menu"
      style={{ left: Math.min(menu.x, window.innerWidth - 250), top: Math.min(menu.y, window.innerHeight - 200) }}
      onClick={(e) => e.stopPropagation()}
    >
      <p className={styles.menuAddress}>{menu.loading ? "주소를 찾는 중..." : label}</p>
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          className={styles.menuItem}
          onClick={() => {
            item.onSelect(place);
            onClose();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
