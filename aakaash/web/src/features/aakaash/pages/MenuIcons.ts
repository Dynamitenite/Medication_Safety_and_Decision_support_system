import { ArrowsLeftRight, ClockCounterClockwise, PlusCircle, UserCircle } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

export const MENU_ICONS: Record<string, Icon> = {
  profile: UserCircle,
  history: ClockCounterClockwise,
  add: PlusCircle,
  alternatives: ArrowsLeftRight,
};
