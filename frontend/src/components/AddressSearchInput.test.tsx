import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddressSearchInput } from "./AddressSearchInput";

const searchAddressSuggestions = vi.fn();
vi.mock("@/lib/place", () => ({
  searchAddressSuggestions: (...args: unknown[]) => searchAddressSuggestions(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

it.each(["출발지 주소", "도착지 주소"])("does not open suggestions when a map selection fills %s", async (ariaLabel) => {
  vi.useFakeTimers();
  const place = { label: "경기도 수원시 권선구 권중로 99", lat: 37.25, lng: 127.03 };
  searchAddressSuggestions.mockResolvedValue([place]);
  const props = { onChange: vi.fn(), onSelect: vi.fn(), ariaLabel };
  const { rerender } = render(<AddressSearchInput value="" {...props} />);
  rerender(<AddressSearchInput value={place.label} {...props} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });

  expect(screen.getByRole("combobox", { name: ariaLabel })).toHaveValue(place.label);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(searchAddressSuggestions).not.toHaveBeenCalled();
});

it("shows matching address candidates and selects only the clicked address", async () => {
  const selected = vi.fn();
  const changed = vi.fn();
  searchAddressSuggestions.mockResolvedValue([
    { label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 },
    { label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 },
  ]);
  const props = { onChange: changed, onSelect: selected, ariaLabel: "주소 검색" };
  const { rerender } = render(<AddressSearchInput value="" {...props} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수원시 영통구 망포" } });
  rerender(<AddressSearchInput value="수원시 영통구 망포" {...props} />);

  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  expect(selected).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("option", { name: "경기도 수원시 영통구 망포로 10" }));
  expect(selected).toHaveBeenCalledWith({ label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 });
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("does not show an older response after the input changes", async () => {
  let finishOld!: (places: { label: string; lat: number; lng: number }[]) => void;
  searchAddressSuggestions.mockImplementation((query: string) => query === "수원" ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve([{ label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 }]));
  const props = { onChange: vi.fn(), onSelect: vi.fn(), ariaLabel: "주소 검색" };
  const { rerender } = render(<AddressSearchInput value="" {...props} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수원" } });
  rerender(<AddressSearchInput value="수원" {...props} />);
  await waitFor(() => expect(searchAddressSuggestions).toHaveBeenCalledWith("수원"));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "망포" } });
  rerender(<AddressSearchInput value="망포" {...props} />);
  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  finishOld([{ label: "경기도 수원시 팔달구 인계동", lat: 37.26, lng: 127.03 }]);
  await waitFor(() => expect(screen.queryByRole("option", { name: "경기도 수원시 팔달구 인계동" })).not.toBeInTheDocument());
});
