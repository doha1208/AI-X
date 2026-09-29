"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { endSession } from "@/lib/auth";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import {
  isValidPhone,
  loadEmergencyContacts,
  loadRecent,
  loadSettings,
  saveEmergencyContacts,
  saveSettings,
  type EmergencyContact,
  type RecentEntry,
  type Settings,
  type TimeMode,
} from "@/lib/preferences";
import { AppHeader } from "@/components/AppHeader";
import { CloseIcon, InfoIcon, MapPinIcon, PhoneIcon, PlusIcon, SearchIcon } from "@/components/icons";
import styles from "./me.module.css";

function timeAgo(at: number, now: number): string {
  const minutes = Math.floor((now - at) / 60_000);
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "어제" : `${days}일 전`;
}

type RecentCardProps = { title: string; icon: React.ReactNode; entries: RecentEntry[]; empty: string; now: number };

function RecentCard({ title, icon, entries, empty, now }: RecentCardProps) {
  return (
    <section className={styles.card}>
      <h2 className={styles.cardTitle}>
        {icon}
        {title}
      </h2>
      {entries.length === 0 ? (
        <p className={styles.empty}>{empty}</p>
      ) : (
        <ul className={styles.recentList}>
          {entries.map((entry) => (
            <li key={entry.label} className={styles.recentItem}>
              <span>{entry.label}</span>
              <span className={styles.recentTime}>{timeAgo(entry.at, now)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function MyInfoPage() {
  const router = useRouter();
  const user = useSessionUser();
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [recentSearches] = useState(() => loadRecent("searches"));
  const [recentDestinations] = useState(() => loadRecent("destinations"));
  const [now] = useState(() => Date.now());
  const [contacts, setContacts] = useState<EmergencyContact[]>(loadEmergencyContacts);
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");

  function addContact(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = contactName.trim();
    const phone = contactPhone.trim();
    if (!isValidPhone(phone)) return;
    const next = [...contacts, { name: name || "보호자", phone }];
    setContacts(next);
    saveEmergencyContacts(next);
    setContactName("");
    setContactPhone("");
  }

  function removeContact(index: number) {
    const next = contacts.filter((_, i) => i !== index);
    setContacts(next);
    saveEmergencyContacts(next);
  }

  function updateSettings(patch: Partial<Settings>) {
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveSettings(next);
      return next;
    });
  }

  async function handleLogout() {
    try {
      await endSession();
    } finally {
      router.replace("/login");
    }
  }

  if (!user) return null;
  const displayName = user.email.split("@")[0] || "회원";

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />

      <div className={styles.shell}>
        <section className={styles.profile}>
          <span className={styles.avatar}>{userInitial(user)}</span>
          <h1 className={styles.name}>{displayName}</h1>
          <p className={styles.email}>{user.email}</p>
        </section>

        <div className={styles.recentGrid}>
          <RecentCard
            title="최근 검색 동네"
            icon={<SearchIcon size={16} />}
            entries={recentSearches}
            empty="아직 검색한 동네가 없어요"
            now={now}
          />
          <RecentCard
            title="최근 목적지"
            icon={<MapPinIcon size={16} />}
            entries={recentDestinations}
            empty="아직 길찾기 기록이 없어요"
            now={now}
          />
        </div>

        <section className={`${styles.card} ${styles.settingsCard}`}>
          <h2 className={styles.settingsHeader}>서비스 설정</h2>

          <div className={styles.settingRow}>
            <div>
              <p className={styles.settingLabel} id="bell-setting">지도에 안전비상벨 표시</p>
              <p className={styles.settingHint}>경로 주변의 비상벨 위치를 지도에 보여줍니다.</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.showBells}
              aria-labelledby="bell-setting"
              className={`${styles.switch} ${settings.showBells ? styles.switchOn : ""}`}
              onClick={() => updateSettings({ showBells: !settings.showBells })}
            >
              <span className={styles.switchKnob} />
            </button>
          </div>

          <div className={styles.settingRow}>
            <div>
              <label className={styles.settingLabel} htmlFor="time-mode">
                안전지수 시간대 기준
              </label>
              <p className={styles.settingHint}>자동이면 현재 시각(밤 22시~6시)에 맞춰 가중치를 바꿉니다.</p>
            </div>
            <select
              id="time-mode"
              className={styles.select}
              value={settings.timeMode}
              onChange={(e) => updateSettings({ timeMode: e.target.value as TimeMode })}
            >
              <option value="auto">자동 (추천)</option>
              <option value="day">항상 낮 기준</option>
              <option value="night">항상 밤 기준</option>
            </select>
          </div>

          <div className={styles.settingRow}>
            <div>
              <p className={styles.settingLabel} id="keep-screen-on-setting">길안내 중 화면 꺼지지 않게 하기</p>
              <p className={styles.settingHint}>
                걷는 동안 화면이 꺼지면 위치 갱신과 음성 안내가 함께 멈춰요. 배터리는 더 빨리 닳을 수 있어요.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.keepScreenOn}
              aria-labelledby="keep-screen-on-setting"
              className={`${styles.switch} ${settings.keepScreenOn ? styles.switchOn : ""}`}
              onClick={() => updateSettings({ keepScreenOn: !settings.keepScreenOn })}
            >
              <span className={styles.switchKnob} />
            </button>
          </div>
        </section>

        <section className={`${styles.card} ${styles.settingsCard}`}>
          <h2 className={styles.settingsHeader}>
            <PhoneIcon size={16} />
            긴급 연락처
          </h2>
          <div className={styles.contactsBody}>
            <p className={styles.settingHint}>
              길안내 화면의 SOS에서 여기 등록한 번호로 현재 위치 문자를 보낼 수 있어요. 이 기기에만 저장돼요.
            </p>
            {contacts.length > 0 && (
              <ul className={styles.recentList}>
                {contacts.map((contact, index) => (
                  <li key={`${contact.phone}-${index}`} className={styles.recentItem}>
                    <span>
                      {contact.name} · {contact.phone}
                    </span>
                    <button
                      type="button"
                      className={styles.contactRemove}
                      onClick={() => removeContact(index)}
                      aria-label={`${contact.name} 연락처 삭제`}
                    >
                      <CloseIcon size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {contacts.length < 3 && (
              <form className={styles.contactForm} onSubmit={addContact}>
                <input
                  className={styles.contactInput}
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  placeholder="이름 (예: 엄마)"
                  aria-label="연락처 이름"
                />
                <input
                  className={styles.contactInput}
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  placeholder="전화번호"
                  inputMode="tel"
                  aria-label="전화번호"
                  required
                />
                <button type="submit" className={styles.contactAdd} aria-label="연락처 추가">
                  <PlusIcon size={16} />
                </button>
              </form>
            )}
          </div>
        </section>

        <section className={styles.infoCard}>
          <h2 className={styles.infoTitle}>
            <InfoIcon size={16} />
            안전지수 계산 방식 안내
          </h2>
          <p className={styles.infoText}>
            안전지수는 <strong>CCTV·보안등 개수, 1만 명당 범죄율(유동인구 반영), 가까운 경찰서·안전비상벨까지의 거리,
            상점 밀도, 교통사고 다발지역과의 거리</strong>를 종합해 계산해요. 밤에는 보안등과 비상벨의 비중을 더 높여
            계산합니다.
          </p>
        </section>

        <button type="button" className={styles.logoutButton} onClick={handleLogout}>
          로그아웃
        </button>
      </div>
    </main>
  );
}
