"use client";

import { AppHeader } from "@/components/AppHeader";
import { InfoIcon } from "@/components/icons";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import styles from "../me/me.module.css";

// ponytail: 기준 시점은 데이터를 다시 받을 때 손으로 고친다 — 갱신 주기가 월~연 단위라 자동화할 만큼 잦지 않다.
const SOURCES = [
  { item: "범죄 발생 건수", source: "경찰청 범죄 발생 지역별 통계 (공공데이터포털)", basis: "2024년", note: "시·군 단위 → 주민등록인구 1만 명당 범죄율" },
  { item: "주민등록인구", source: "행정안전부 주민등록 인구 및 세대현황", basis: "2024년 월평균", note: "범죄율의 분모" },
  { item: "CCTV (생활방범)", source: "전국CCTV표준데이터 (공공데이터포털)", basis: "2026년 9월 수집", note: "부천·광명·화성은 제출 자료가 거의 없어 제외" },
  { item: "보안등", source: "전국보안등정보표준데이터 OpenAPI", basis: "2026년 9월 수집", note: "" },
  { item: "안전비상벨", source: "전국안전비상벨위치표준데이터", basis: "2026년 9월 수집", note: "의정부·부천·광명·고양·오산·안성·화성·포천·여주·양평은 제출 자료가 거의 없어 제외" },
  { item: "교통사고 다발지역", source: "전국교통사고다발지역표준데이터", basis: "2022~2024년 사고", note: "최근 3년치만 사용" },
  { item: "상점·편의점", source: "소상공인시장진흥공단 상가(상권)정보", basis: "2026년 6월", note: "길가(1층·지하1층) 음식·소매 상점만 셈. 밤에는 편의점만 가점" },
  { item: "유흥주점·단란주점", source: "행정안전부 지방행정 인허가 (영업 중)", basis: "2026년 10월 수집", note: "밤에 근처 길은 감점" },
  { item: "야간 유동인구 (22~05시)", source: "경기데이터드림 유동인구_행정동 단위 집계 (KT 통신 데이터)", basis: "2026년 1~3월", note: "참여한 16개 시·군(367개 동)만 반영" },
  { item: "경찰서·공원·하천, 보행 도로망", source: "OpenStreetMap", basis: "2026년 9월", note: "" },
  { item: "행정동 경계", source: "통계청 SGIS 행정동 경계 (vuski/admdongkor 가공)", basis: "", note: "" },
];

export default function DataSourcesPage() {
  const user = useSessionUser();
  if (!user) return null;

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />
      <div className={styles.shell}>
        <section className={styles.infoCard}>
          <h1 className={styles.infoTitle}>
            <InfoIcon size={16} />
            데이터 출처와 기준
          </h1>
          <p className={styles.infoText}>
            안전지수는 아래 공개 데이터를 경기도 행정동 단위로 비교한 <strong>상대 점수</strong>예요. 지자체가 데이터를
            제출하지 않았거나 제공 범위 밖인 지역은 그 항목을 <strong>점수 계산에서 빼고</strong> 나머지 항목만으로
            계산해요 — 없는 데이터를 0이나 중간값으로 채우지 않아요.
          </p>
        </section>

        {SOURCES.map(({ item, source, basis, note }) => (
          <section key={item} className={styles.card}>
            <h2 className={styles.cardTitle}>{item}</h2>
            <p className={styles.infoText}>
              {source}
              {basis && <> · <strong>{basis}</strong></>}
            </p>
            {note && <p className={styles.infoText}>{note}</p>}
          </section>
        ))}

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>저작권 표시</h2>
          <p className={styles.infoText}>
            경기데이터드림 유동인구 데이터: 공공누리 제2유형(출처표시, 상업적 이용금지). 지도 도로망·시설: © OpenStreetMap
            contributors (ODbL). 행정동 경계: 통계청 SGIS, vuski/admdongkor 가공 (CC BY 4.0).
          </p>
          <p className={styles.infoText}>이 점수와 추천 경로는 참고 정보이며, 실제 안전을 보장하지 않아요.</p>
        </section>
      </div>
    </main>
  );
}
