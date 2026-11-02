import type { ComponentType } from "react";
import { Checker } from "./pages/Checker";
import { Home } from "./pages/Home";

/** Pages that open by URL but are not menu items. (Data & methods and the paper trace are footer-linked
 *  routes in App.tsx; the pending modules are in MODULE_COMPONENTS.) */
export type Screen = { id: string; path: string; label: string; Component: ComponentType };

export const SCREENS: Screen[] = [
  { id: "search", path: "/search", label: "Search", Component: Home },
  { id: "checker", path: "/checker", label: "Interaction Checker", Component: Checker },
];

/** The four options of the signed-in menu, in order. "Add new medicine" and "Alternative medicines"
 *  open the existing search and alternatives pages until the scan and similar-use pages replace them. */
export type MenuItem = { id: "profile" | "history" | "add" | "alternatives"; path: string; label: string; blurb: string };

export const MENU: MenuItem[] = [
  { id: "profile", path: "/profile", label: "My profile", blurb: "Your details, current conditions and allergies." },
  { id: "history", path: "/history", label: "Past and current medical history", blurb: "Conditions and medicines, with dates and outcomes." },
  { id: "add", path: "/search", label: "Add new medicine", blurb: "Look up a medicine and check it against the others you take." },
  { id: "alternatives", path: "/alternatives", label: "Alternative medicines", blurb: "Find other brands with the same ingredients." },
];

/**
 * The list of pending modules (names, stages, owners) comes from the API (GET /api/status, owned by
 * api/modules.py). Nothing about them is written here. This file only says which React component
 * replaces a placeholder. To replace one:
 *   1. add your feature folder (for example src/features/<you>/AllergyCheck.tsx);
 *   2. add one line below: `allergy_check: AllergyCheck,`  (the id is the API's module id);
 *   3. change the module's entry in api/modules.py / the API so it stops reporting coming_soon.
 * Modules without an entry here render the generic "Coming soon" page. They are reachable by URL
 * (/modules/<id>) and listed on /about/data.
 */
export const MODULE_COMPONENTS: Record<string, ComponentType> = {};

export const modulePath = (id: string) => `/modules/${id}`;
