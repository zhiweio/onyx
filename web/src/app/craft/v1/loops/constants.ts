import type { Route } from "next";

import { CRAFT_PATH } from "@/app/craft/v1/constants";

export const LOOPS_PATH = `${CRAFT_PATH}/loops` as Route;

export function loopDetailPath(loopId: string): Route {
  return `${LOOPS_PATH}/${loopId}` as Route;
}
