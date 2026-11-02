import type { ComponentType } from "react";
import { About } from "./pages/About";
import { Checker } from "./pages/Checker";
import { Dashboard } from "./pages/Dashboard";
import { Home } from "./pages/Home";
import { InteractionRisk, PersonalizedAlert } from "./pages/ToBuildPages";
import { Trace } from "./pages/Trace";

/** Screens of this app. (The coming-soon modules are NOT listed here; see MODULE_COMPONENTS.) */
export type Screen = { id: string; path: string; label: string; Component: ComponentType };

export const SCREENS: Screen[] = [
  { id: "home", path: "/", label: "Search", Component: Home },
  { id: "checker", path: "/checker", label: "Interaction Checker", Component: Checker },
  { id: "dashboard", path: "/dashboard", label: "Dashboard", Component: Dashboard },
  { id: "interaction_risk", path: "/interaction-risk", label: "Interaction Risk", Component: InteractionRisk },
  { id: "personalized_alert", path: "/personalized-alert", label: "Personalized Alert", Component: PersonalizedAlert },
  { id: "trace", path: "/trace", label: "Trace", Component: Trace },
  { id: "about", path: "/about", label: "About", Component: About },
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
