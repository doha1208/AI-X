"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login } from "@/lib/api";
import {
  EyeIcon,
  EyeOffIcon,
  KakaoIcon,
  LockIcon,
  MailIcon,
  MapPinIcon,
  ShieldHeartIcon,
} from "@/components/icons";
import styles from "@/styles/auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password, rememberMe);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <div className={`${styles.logo} ${styles.logoLg}`}>
          <ShieldHeartIcon size={44} />
          <span className={`${styles.logoBadge} ${styles.logoBadgeLg}`}>
            <MapPinIcon size={18} />
          </span>
        </div>
        <h1 className={styles.title}>안심 거주지</h1>
        <p className={styles.subtitle}>
          우리 동네 안전지수를 확인하고
          <br />
          든든한 귀갓길을 찾아보세요
        </p>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">
              이메일
            </label>
            <div className={styles.inputWrap}>
              <span className={styles.inputIcon}>
                <MailIcon />
              </span>
              <input
                id="email"
                className={styles.input}
                type="email"
                placeholder="example@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              비밀번호
            </label>
            <div className={styles.inputWrap}>
              <span className={styles.inputIcon}>
                <LockIcon />
              </span>
              <input
                id="password"
                className={styles.input}
                type={showPassword ? "text" : "password"}
                placeholder="비밀번호를 입력해주세요"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className={styles.toggleVisibility}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 표시"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </div>

          <div className={styles.rowBetween}>
            <label className={styles.rememberMe}>
              <input
                type="checkbox"
                className={styles.checkbox}
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              로그인 상태 유지
            </label>
            <Link href="#" className={styles.link}>
              비밀번호 찾기
            </Link>
          </div>

          {error && <p className={styles.formError}>{error}</p>}

          <button type="submit" className={styles.submit} disabled={loading}>
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className={styles.divider}>또는</div>

        <button type="button" className={styles.kakaoButton} disabled title="추후 지원 예정">
          <KakaoIcon size={22} />
          카카오로 시작하기
        </button>

        <p className={styles.switchText}>
          아직 계정이 없으신가요? <Link href="/signup">회원가입</Link>
        </p>
      </div>
    </main>
  );
}
