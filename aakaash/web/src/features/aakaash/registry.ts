import type { ComponentType } from "react";
import { Checker } from "./pages/Checker";
import { Home } from "./pages/Home";

/** Screens in the main navigation. (Data & methods and the paper trace are footer-linked routes in App.tsx; the coming-soon modules are in MODULE_COMPONENTS.) */
export type Screen = { id: string; path: string; label: string; Component: ComponentType };

export const SCREENS: Screen[] = [
  { id: "home", path: "/", label: "Search", Component: Home },
  { id: "checker", path: "/checker", label: "Interaction Checker", Component: Checker },
];

/**
 * The list of pending modules (names, stages, owners) comes from the API (GET /api/status, owned by
 * api/modules.py). Nothing about them is written here. This file only says which React component
 * replaces a placeholder. To replace one:
 *   1. add your feature folder (for example src/features/<you>/AllergyCheck.tsx);
 *   2. add one line below: `allergy_check: AllergyCheck,`  (the id is the API's module id);
 *   3. change the module's entry in api/modules.py / the API so it stops reporting coming_soon.
 * Modules without an entry here render the generic "Coming soon" page.
 */
export const MODULE_COMPONENTS: Record<string, ComponentType> = {};

export const modulePath = (id: string) => `/modules/${id}`;
