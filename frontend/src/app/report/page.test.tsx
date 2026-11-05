import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ReportPage from "./page";
import type { SpotReport } from "@/lib/api";
import { environmentRouteFixture } from "@/test/routeFixtures";

const suggestions = vi.fn();
const resolvePlace = vi.fn();
const spotReport = vi.fn();
const routeSafety = vi.fn();
const nearestSubway = vi.fn();
const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/report",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));
vi.mock("@/lib/useSessionUser", () => ({
  useSessionUser: () => ({ id: 1, email: "test@example.com" }),
  userInitial: () => "T",
}));
vi.mock("@/lib/place", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/place")>(),
  searchAddressSuggestions: (...args: unknown[]) => suggestions(...args),
  resolvePlace: (...args: unknown[]) => resolvePlace(...args),
}));
vi.mock("@/lib/api", () => ({ spotReport: (...args: unknown[]) => spotReport(...args), routeSafety: (...args: unknown[]) => routeSafety(...args) }));
vi.mock("@/lib/kakao", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/kakao")>(), nearestSubway: (...args: unknown[]) => nearestSubway(...args),
}));

beforeEach(() => {
  vi.clearAllMocks();
  navigation.search = "";
  nearestSubway.mockResolvedValue(null);
  suggestions.mockResolvedValue([{ label: "경기도 수원시 효원로 241", lat: 37.263, lng: 127.028 }]);
  spotReport.mockResolvedValue({ lat: 37.263, lng: 127.028, period: "day", radius_m: 300, zone: null,
    here_score: null, area_day_score: null, area_night_score: null, counts: null, havens: [] } satisfies SpotReport);
});

it("uses the selected home address coordinates without geocoding the label again", async () => {
  render(<ReportPage />);
  fireEvent.change(screen.getByRole("combobox", { name: "집 주소" }), { target: { value: "수원시 효원로" } });
  fireEvent.click(await screen.findByRole("option", { name: "경기도 수원시 효원로 241" }));
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  fireEvent.submit(screen.getByRole("search"));
  await waitFor(() => expect(spotReport).toHaveBeenCalledWith(37.263, 127.028));
  expect(resolvePlace).not.toHaveBeenCalled();
});

it("hides home address candidates when focus leaves the address input", async () => {
  render(<ReportPage />);
  const input = screen.getByRole("combobox", { name: "집 주소" });
  fireEvent.change(input, { target: { value: "수원시 효원로" } });
  expect(await screen.findByRole("listbox")).toBeInTheDocument();
  fireEvent.blur(input, { relatedTarget: screen.getByRole("button", { name: "리포트 보기" }) });
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("reloads when the same selected address is explicitly submitted again", async () => {
  render(<ReportPage />);
  fireEvent.change(screen.getByRole("combobox", { name: "집 주소" }), { target: { value: "수원시 효원로" } });
  fireEvent.click(await screen.findByRole("option", { name: "경기도 수원시 효원로 241" }));
  fireEvent.submit(screen.getByRole("search"));
  await waitFor(() => expect(spotReport).toHaveBeenCalledTimes(1));
  fireEvent.submit(screen.getByRole("search"));
  await waitFor(() => expect(spotReport).toHaveBeenCalledTimes(2));
  expect(screen.queryByText(/분석하는 중/)).not.toBeInTheDocument();
});

it("reloads a prefilled address when its report button is pressed", async () => {
  navigation.search = "at=37.263,127.028&atName=수원시청";
  render(<ReportPage />);
  await waitFor(() => expect(spotReport).toHaveBeenCalledTimes(1));
  fireEvent.submit(screen.getByRole("search"));
  await waitFor(() => expect(spotReport).toHaveBeenCalledTimes(2));
});

it("shows the returned facility assessment for the night walk when legacy safety_score is null", async () => {
  navigation.search = "at=37.263,127.028&atName=수원시청";
  nearestSubway.mockResolvedValue({ name: "수원시청역", lat: 37.262, lng: 127.03 });
  routeSafety.mockResolvedValue(environmentRouteFixture());
  render(<ReportPage />);
  expect(await screen.findByText("시설 97점")).toBeInTheDocument();
  expect(screen.queryByText("안전지수 미제공")).not.toBeInTheDocument();
});
