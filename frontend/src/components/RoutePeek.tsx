"use client";

import { NavigationIcon } from "@/components/icons";
import styles from "./RoutePeek.module.css";

export type RoutePeekItem = {
  key: string;
  label: string;
  minutes: number;
  distance: string;
  score?: string;
  active: boolean;
};

type Props = {
  items: RoutePeekItem[];
  onSelect: (key: string) => void;
  onStart: () => void;
};

// 하단 시트가 접힌 채로도 경로를 골라 보고 바로 안내를 시작할 수 있게 하는 한 줄 요약(지도앱의 경로 칩).
// 시트를 펼치면 자세한 카드가 나오고, 여기서는 지도를 가리지 않는 높이로 시간·거리·점수만 보여준다.
export function RoutePeek({ items, onSelect, onStart }: Props) {
  return (
    <div className={styles.peek}>
      <div className={styles.chips} role="group" aria-label="경로 선택">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`${styles.chip} ${item.active ? styles.chipActive : ""}`}
            aria-pressed={item.active}
            onClick={() => onSelect(item.key)}
          >
            <span className={styles.chipLabel}>{item.label}</span>
            <strong className={styles.chipTime}>{item.minutes}분</strong>
            <span className={styles.chipMeta}>
              {item.distance}
              {item.score ? ` · ${item.score}` : ""}
            </span>
          </button>
        ))}
      </div>
      <button type="button" className={styles.start} onClick={onStart}>
        <NavigationIcon size={16} />
        안내 시작
      </button>
    </div>
  );
}
