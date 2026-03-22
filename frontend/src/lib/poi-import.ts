export type DiningCategory = "lunch" | "dinner";

export function requiresDiningCategoryChoice(
  primaryType: string | null | undefined,
): boolean {
  if (!primaryType) {
    return false;
  }
  const lowered = primaryType.toLowerCase();
  return (
    lowered.includes("restaurant")
    || lowered.includes("food")
    || lowered.includes("meal")
  );
}
