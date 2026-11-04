import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddressSearchInput } from "./AddressSearchInput";

const searchAddressSuggestions = vi.fn();
vi.mock("@/lib/place", () => ({
  searchAddressSuggestions: (...args: unknown[]) => searchAddressSuggestions(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
});

it("shows matching address candidates and selects only the clicked address", async () => {
  const selected = vi.fn();
  const changed = vi.fn();
  searchAddressSuggestions.mockResolvedValue([
    { label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 },
    { label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 },
  ]);
  render(<AddressSearchInput value="수원시 영통구 망포" onChange={changed} onSelect={selected} ariaLabel="주소 검색" />);

  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  expect(selected).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("option", { name: "경기도 수원시 영통구 망포로 10" }));
  expect(selected).toHaveBeenCalledWith({ label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 });
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("does not show an older response after the input changes", async () => {
  let finishOld!: (places: { label: string; lat: number; lng: number }[]) => void;
  searchAddressSuggestions.mockImplementation((query: string) => query === "수원" ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve([{ label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 }]));
  const { rerender } = render(<AddressSearchInput value="수원" onChange={vi.fn()} onSelect={vi.fn()} ariaLabel="주소 검색" />);
  await waitFor(() => expect(searchAddressSuggestions).toHaveBeenCalledWith("수원"));
  rerender(<AddressSearchInput value="망포" onChange={vi.fn()} onSelect={vi.fn()} ariaLabel="주소 검색" />);
  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  finishOld([{ label: "경기도 수원시 팔달구 인계동", lat: 37.26, lng: 127.03 }]);
  await waitFor(() => expect(screen.queryByRole("option", { name: "경기도 수원시 팔달구 인계동" })).not.toBeInTheDocument());
});
