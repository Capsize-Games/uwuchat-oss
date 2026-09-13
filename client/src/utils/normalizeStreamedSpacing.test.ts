import { describe, expect, it } from "vitest";

import { normalizeStreamedSpacing } from "./normalizeStreamedSpacing";

describe("normalizeStreamedSpacing", () => {
  it("collapses spaces inside digit runs", () => {
    expect(normalizeStreamedSpacing("The issue number is 1 2 3")).toBe(
      "The issue number is 123",
    );
    expect(normalizeStreamedSpacing("2 0 2 6")).toBe("2026");
  });

  it("preserves hex identifiers", () => {
    expect(normalizeStreamedSpacing("airunner-71a8e2d7")).toBe(
      "airunner-71a8e2d7",
    );
  });

  it("preserves commit SHAs and versions", () => {
    expect(normalizeStreamedSpacing("commit 1ab328d25")).toBe(
      "commit 1ab328d25",
    );
    expect(normalizeStreamedSpacing("gh 2.98.0, issue #162")).toBe(
      "gh 2.98.0, issue #162",
    );
  });

  it("preserves ordinary word spacing", () => {
    expect(normalizeStreamedSpacing("I need to check the repo")).toBe(
      "I need to check the repo",
    );
  });

  it("returns empty input unchanged", () => {
    expect(normalizeStreamedSpacing("")).toBe("");
    expect(normalizeStreamedSpacing(null as unknown as string)).toBeNull();
  });
});
