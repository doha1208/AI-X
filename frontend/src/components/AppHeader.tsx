"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BellIcon, ShieldPinIcon } from "@/components/icons";
import styles from "./AppHeader.module.css";

const TABS = [
  { href: "/", label: "안심 거주지" },
  { href: "/route", label: "길찾기" },
  { href: "/navigate", label: "길안내" },
  { href: "/me", label: "내 정보" },
];

type Props = { userInitial: string };

export function AppHeader({ userInitial }: Props) {
  const pathname = usePathname();

  return (
    <header className={styles.header}>
      <Link href="/" className={styles.brand}>
        <span className={styles.brandIcon}>
          <ShieldPinIcon size={18} />
        </span>
        안심 <span className={styles.brandAccent}>거주지</span>
      </Link>

      <nav className={styles.tabs} aria-label="주요 메뉴">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`${styles.tab} ${active ? styles.tabActive : ""}`}
              aria-current={active ? "page" : undefined}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      <div className={styles.actions}>
        <button type="button" className={styles.bellButton} aria-label="알림 (준비 중)" title="준비 중">
          <BellIcon size={18} />
        </button>
        <Link href="/me" className={styles.avatar} aria-label="내 정보">
          {userInitial}
        </Link>
      </div>
    </header>
  );
}
