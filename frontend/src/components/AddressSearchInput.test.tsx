import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddressSearchInput } from "./AddressSearchInput";
import { useState } from "react";
import type { Place } from "@/lib/place";

const searchAddressSuggestions = vi.fn();
vi.mock("@/lib/place", () => ({
  searchAddressSuggestions: (...args: unknown[]) => searchAddressSuggestions(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function EditableInput({ selected = () => undefined }: { selected?: (place: Place) => void }) {
  const [value, setValue] = useState("");
  return <AddressSearchInput value={value} onChange={setValue} onSelect={(place) => { setValue(place.label); selected(place); }} ariaLabel="주소 검색" />;
}

it("shows matching address candidates and selects only the clicked address", async () => {
  const selected = vi.fn();
  searchAddressSuggestions.mockResolvedValue([
    { label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 },
    { label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 },
  ]);
  render(<EditableInput selected={selected} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수원시 영통구 망포" } });

  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  expect(selected).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("option", { name: "경기도 수원시 영통구 망포로 10" }));
  expect(selected).toHaveBeenCalledWith({ label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 });
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("does not show an older response after the input changes", async () => {
  let finishOld!: (places: { label: string; lat: number; lng: number }[]) => void;
  searchAddressSuggestions.mockImplementation((query: string) => query === "수원" ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve([{ label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 }]));
  render(<EditableInput />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수원" } });
  await waitFor(() => expect(searchAddressSuggestions).toHaveBeenCalledWith("수원"));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "망포" } });
  expect(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" })).toBeInTheDocument();
  finishOld([{ label: "경기도 수원시 팔달구 인계동", lat: 37.26, lng: 127.03 }]);
  await waitFor(() => expect(screen.queryByRole("option", { name: "경기도 수원시 팔달구 인계동" })).not.toBeInTheDocument());
});

it("does not search or reopen candidates for an externally supplied address", async () => {
  const { rerender } = render(<AddressSearchInput value="" onChange={vi.fn()} onSelect={vi.fn()} ariaLabel="주소 검색" />);
  rerender(<AddressSearchInput value="경기도 수원시 효원로 241" onChange={vi.fn()} onSelect={vi.fn()} ariaLabel="주소 검색" />);
  fireEvent.focus(screen.getByRole("combobox"));
  await new Promise(resolve => setTimeout(resolve, 300));
  expect(searchAddressSuggestions).not.toHaveBeenCalled();
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("dismisses candidates on outside pointer interaction even when focus does not change", async () => {
  searchAddressSuggestions.mockResolvedValue([{ label: "경기도 수원시 효원로 241", lat: 37.263, lng: 127.028 }]);
  render(<EditableInput />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수원시 효원로" } });
  expect(await screen.findByRole("listbox")).toBeInTheDocument();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});
