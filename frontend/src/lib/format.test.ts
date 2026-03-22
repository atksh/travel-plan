import { describe, expect, it } from "vitest";
import { localDateInputValue } from "@/lib/format";

describe("localDateInputValue", () => {
  it("formats the local calendar date for date inputs", () => {
    expect(localDateInputValue(new Date(2026, 2, 22, 7, 30))).toBe("2026-03-22");
  });
});
