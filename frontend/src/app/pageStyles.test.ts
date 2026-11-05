import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, expect, it } from "vitest";

afterEach(() => {
  document.head.querySelector("style[data-residence-styles-test]")?.remove();
  document.body.replaceChildren();
});

it("lets the entire statistics content scroll when the fixed search leaves little room", () => {
  const style = document.createElement("style");
  style.dataset.residenceStylesTest = "true";
  style.textContent = readFileSync(path.resolve(process.cwd(), "src/app/page.module.css"), "utf8");
  document.head.append(style);
  const content = document.createElement("div");
  content.className = "panelContent";
  content.innerHTML = '<header class="panelHeader"></header><ol class="rankList"></ol><footer class="panelFooter"></footer>';
  document.body.append(content);
  expect(getComputedStyle(content).overflowY).toBe("auto");
  // A long list must retain its content height so the parent can scroll to every row.
  expect(getComputedStyle(content.querySelector(".rankList")!).flexShrink).toBe("0");
});
