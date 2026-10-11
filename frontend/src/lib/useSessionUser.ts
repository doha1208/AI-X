"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@/lib/api";
import { getSessionUser } from "@/lib/auth";

// undefined = 확인 중, null = 비로그인(로그인 화면으로 보냄).
export function useSessionUser(): User | null | undefined {
  const router = useRouter();
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    let active = true;
    void getSessionUser()
      .then((u) => { if (active) setUser(u); })
      .catch(() => { if (active) { setUser(null); router.replace("/login"); } });
    return () => { active = false; };
  }, [router]);

  return user;
}

export function userInitial(user: User): string {
  return (user.email.split("@")[0] || "회원").slice(0, 1).toUpperCase();
}
