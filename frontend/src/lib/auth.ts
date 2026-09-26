import { logout, me, type User } from "@/lib/api";

export function getSessionUser(): Promise<User> {
  return me();
}

export function endSession(): Promise<void> {
  return logout();
}
