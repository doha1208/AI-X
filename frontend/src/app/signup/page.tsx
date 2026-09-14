"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signup } from "@/lib/api";
import {
  ArrowLeftIcon,
  ChevronRightIcon,
  EyeIcon,
  EyeOffIcon,
  HomeIcon,
  InfoIcon,
  LockIcon,
  MailIcon,
} from "@/components/icons";
import styles from "@/styles/auth.module.css";

const REQUIRED_TERMS = ["terms", "privacy"] as const;
type ConsentKey = "terms" | "privacy" | "location";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [consent, setConsent] = useState<Record<ConsentKey, boolean>>({
    terms: false,
    privacy: false,
    location: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const passwordMismatch = confirmPassword.length > 0 && password !== confirmPassword;
  const allConsent = consent.terms && consent.privacy && consent.location;
  const requiredConsentMissing = !REQUIRED_TERMS.every((key) => consent[key]);
  const canSubmit = !passwordMismatch && !requiredConsentMissing && password.length >= 8;

  function toggleConsent(key: ConsentKey) {
    setConsent((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function toggleAllConsent() {
    const next = !allConsent;
    setConsent({ terms: next, privacy: next, location: next });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (passwordMismatch) return;
    if (requiredConsentMissing) {
      setError("필수 약관에 동의해주세요");
      return;
    }
    setLoading(true);
    try {
      await signup(email, password);
      router.push("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <button
          type="button"
          className={styles.back}
          onClick={() => router.back()}
          aria-label="뒤로 가기"
        >
          <ArrowLeftIcon />
        </button>

        <div className={styles.logo}>
          <HomeIcon size={30} />
        </div>
        <h1 className={styles.title}>회원가입</h1>
        <p className={styles.subtitle}>
          안심 거주지와 함께 더 안전한
          <br />
          일상을 시작해보세요
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
                placeholder="8자 이상 입력해주세요"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
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
            <span className={styles.hint}>
              <InfoIcon size={13} /> 영문, 숫자, 특수문자를 포함해주세요
            </span>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="confirmPassword">
              비밀번호 확인
            </label>
            <div className={styles.inputWrap}>
              <span className={styles.inputIcon}>
                <LockIcon />
              </span>
              <input
                id="confirmPassword"
                className={`${styles.input} ${passwordMismatch ? styles.invalid : ""}`}
                type={showPassword ? "text" : "password"}
                placeholder="비밀번호를 한 번 더 입력해주세요"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
            {passwordMismatch && (
              <span className={styles.errorText}>비밀번호가 일치하지 않아요</span>
            )}
          </div>

          <div className={styles.consentBox}>
            <label className={styles.consentAll}>
              <input
                type="checkbox"
                className={styles.checkbox}
                checked={allConsent}
                onChange={toggleAllConsent}
              />
              전체 동의합니다
            </label>
            <label className={styles.consentItem}>
              <span>
                <input
                  type="checkbox"
                  className={styles.checkbox}
                  checked={consent.terms}
                  onChange={() => toggleConsent("terms")}
                />
                [필수] 이용약관 동의
              </span>
              <ChevronRightIcon size={15} />
            </label>
            <label className={styles.consentItem}>
              <span>
                <input
                  type="checkbox"
                  className={styles.checkbox}
                  checked={consent.privacy}
                  onChange={() => toggleConsent("privacy")}
                />
                [필수] 개인정보 수집 및 이용 동의
              </span>
              <ChevronRightIcon size={15} />
            </label>
            <label className={styles.consentItem}>
              <span>
                <input
                  type="checkbox"
                  className={styles.checkbox}
                  checked={consent.location}
                  onChange={() => toggleConsent("location")}
                />
                [선택] 위치기반 서비스 이용 동의
              </span>
              <ChevronRightIcon size={15} />
            </label>
          </div>

          {error && <p className={styles.formError}>{error}</p>}

          <button type="submit" className={styles.submit} disabled={loading || !canSubmit}>
            {loading ? "가입 중..." : "가입하기"}
          </button>
        </form>

        <p className={styles.switchText}>
          이미 계정이 있으신가요? <Link href="/login">로그인</Link>
        </p>
      </div>
    </main>
  );
}
