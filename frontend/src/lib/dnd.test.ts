import { describe, expect, it } from "vitest";
import { moveId } from "@/lib/dnd";

describe("moveId", () => {
  it("moves an item inside an array", () => {
    expect(moveId([1, 2, 3, 4], 0, 2)).toEqual([2, 3, 1, 4]);
  });
});
