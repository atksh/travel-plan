import { describe, expect, it } from "vitest";
import { requiresDiningCategoryChoice } from "@/lib/poi-import";

describe("requiresDiningCategoryChoice", () => {
  it("returns true for generic restaurant types", () => {
    expect(requiresDiningCategoryChoice("restaurant")).toBe(true);
    expect(requiresDiningCategoryChoice("meal_takeaway")).toBe(true);
  });

  it("returns false for non-dining categories", () => {
    expect(requiresDiningCategoryChoice("museum")).toBe(false);
    expect(requiresDiningCategoryChoice("cafe")).toBe(false);
    expect(requiresDiningCategoryChoice(undefined)).toBe(false);
  });
});
