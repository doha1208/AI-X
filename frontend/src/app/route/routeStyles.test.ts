import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(process.cwd(), "src/app/route/route.module.css"), "utf8");

describe("desktop route result sizing", () => {
  afterEach(() => {
    document.head.querySelector("style[data-route-styles-test]")?.remove();
    document.body.replaceChildren();
  });

  it("keeps result boxes at their content height and scrolls the result panel", () => {
    const style = document.createElement("style");
    style.dataset.routeStylesTest = "true";
    style.textContent = css;
    document.head.append(style);

    const results = document.createElement("section");
    results.className = "results";
    const card = document.createElement("article");
    card.className = "routeCard";
    const disclosure = document.createElement("details");
    disclosure.className = "dataDisclosure";
    const notice = document.createElement("p");
    notice.className = "note";
    results.append(notice, disclosure, card);
    document.body.append(results);

    expect(getComputedStyle(results).overflowY).toBe("auto");
    for (const box of [notice, disclosure, card]) {
      expect(getComputedStyle(box).flexShrink).toBe("0");
    }
  });
});
