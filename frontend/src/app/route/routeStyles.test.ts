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

  it("shows only the mobile address workflow before a route is requested", () => {
    // Apply the mobile rules as the viewport rules; jsdom does not evaluate media queries.
    const style = document.createElement("style");
    style.dataset.routeStylesTest = "true";
    style.textContent = css;
    document.head.append(style);
    const mobileRules = Array.from(style.sheet!.cssRules)
      .filter((rule): rule is CSSMediaRule => rule instanceof CSSMediaRule && rule.conditionText === "(max-width: 767px)")
      .flatMap(rule => Array.from(rule.cssRules).map(child => child.cssText)).join("\n");
    style.textContent = css + "\n" + mobileRules;
    const workspace = document.createElement("div");
    workspace.className = "layout";
    workspace.dataset.hasRoute = "false";
    workspace.innerHTML = '<aside class="sidebar"><header></header><section class="mobileFlow"></section><div class="searchPanel"></div><section class="resultsSheet"></section></aside>';
    document.body.append(workspace);
    expect(getComputedStyle(workspace.querySelector(".mobileFlow")!).display).toBe("block");
    expect(getComputedStyle(workspace.querySelector(".searchPanel")!).display).toBe("none");
    expect(getComputedStyle(workspace.querySelector(".resultsSheet")!).display).toBe("none");
    workspace.dataset.hasRoute = "true";
    expect(getComputedStyle(workspace.querySelector(".searchPanel")!).display).not.toBe("none");
  });
});
