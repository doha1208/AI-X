import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";

const nearbyBells = vi.fn();
vi.mock("@/lib/api", () => ({ nearbyBells }));

test("keeps bells from the latest route when an earlier request resolves late", async () => {
  const first = Promise.withResolvers<{ lat: number; lng: number }[]>();
  const second = Promise.withResolvers<{ lat: number; lng: number }[]>();
  nearbyBells.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const { useRouteBells } = await import("./useRouteBells");
  const routeA = [{ lat: 37.5, lng: 127 }];
  const routeB = [{ lat: 37.51, lng: 127.01 }];
  const { result, rerender } = renderHook(({ points }) => useRouteBells(points), { initialProps: { points: routeA } });

  rerender({ points: routeB });
  await act(async () => second.resolve([{ lat: 37.51, lng: 127.01 }]));
  await act(async () => first.resolve([{ lat: 37.5, lng: 127 }]));

  expect(result.current).toEqual([{ lat: 37.51, lng: 127.01 }]);
});
