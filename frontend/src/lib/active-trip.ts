import type { ActiveTripBootstrapOut } from "@/lib/types";

export async function loadActiveTripBootstrap(
  load: () => Promise<ActiveTripBootstrapOut>,
): Promise<ActiveTripBootstrapOut> {
  return load();
}
