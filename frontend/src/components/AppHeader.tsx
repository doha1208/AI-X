"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { HomeIcon, MapPinIcon, RouteIcon, ShieldHeartIcon, ShieldPinIcon } from "@/components/icons";
import styles from "./AppHeader.module.css";

const TABS = [
  { href: "/", label: "안심거주지", icon: HomeIcon },
  { href: "/route", label: "길찾기", icon: RouteIcon },
];
const SECONDARY = [
  { href: "/report", label: "집 리포트", icon: MapPinIcon },
  { href: "/me", label: "내 정보", icon: ShieldHeartIcon },
  { href: "/data", label: "데이터 출처", icon: ShieldPinIcon },
];

type Props = { userInitial: string; variant?: "default" | "panel" };

export function AppHeader({ userInitial, variant = "default" }: Props) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <header ref={rootRef} className={[styles.header, variant === "panel" ? styles.panel : ""].join(" ")}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}>
      <button ref={buttonRef} type="button" className={styles.menuToggle}
        aria-label={open ? "메뉴 닫기" : "메뉴 열기"} aria-expanded={open} aria-controls={menuId}
        onClick={() => setOpen(value => !value)}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          {open ? <path d="m6 6 12 12M6 18 18 6" /> : <path d="M4 6h16M4 12h16M4 18h16" />}
        </svg>
        <span className={styles.menuLabel}>메뉴</span>
      </button>
      <Link href="/" className={styles.brand} onClick={() => setOpen(false)}>
        <span className={styles.brandIcon}><ShieldPinIcon size={21} /></span>
        안심 거주지
      </Link>
      <nav className={styles.tabs} aria-label="주요 메뉴">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href === "/route" && pathname === "/navigate");
          return <Link key={href} href={href} onClick={() => setOpen(false)}
            className={[styles.tab, active ? styles.tabActive : ""].join(" ")} aria-current={active ? "page" : undefined}>
            <Icon size={18} /><span>{label}</span>
          </Link>;
        })}
      </nav>
      {open && <nav id={menuId} className={styles.menu} aria-label="기타 메뉴">
        <div className={styles.menuHeading}><span className={styles.avatar} aria-hidden="true">{userInitial}</span><span>안심 거주지 메뉴</span></div>
        {SECONDARY.map(({ href, label, icon: Icon }) => <Link key={href} href={href}
          className={styles.menuLink} aria-current={pathname === href ? "page" : undefined} onClick={() => setOpen(false)}>
          <Icon size={19} /><span>{label}</span><span className={styles.arrow} aria-hidden="true">›</span>
        </Link>)}
      </nav>}
    </header>
  );
}
