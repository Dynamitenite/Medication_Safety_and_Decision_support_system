import { useEffect } from "react";

const SELECTOR = ".table-wrap, .timeline-svg, .price-chart";

/** Wide tables and charts scroll sideways inside their card on a phone. A box that scrolls has to be
 *  reachable with the keyboard, so each one that really overflows gets a tab stop (and loses it when it fits). */
export function useScrollRegions() {
  useEffect(() => {
    let frame = 0;
    const mark = () => {
      frame = 0;
      document.querySelectorAll<HTMLElement>(SELECTOR).forEach((el) => {
        const overflows = el.scrollWidth > el.clientWidth + 1;
        if (overflows && !el.hasAttribute("tabindex")) {
          el.tabIndex = 0;
          el.dataset.scrollRegion = "1";
        } else if (!overflows && el.dataset.scrollRegion) {
          el.removeAttribute("tabindex");
          delete el.dataset.scrollRegion;
        }
      });
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(mark);
    };
    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", schedule);
    schedule();
    return () => {
      mo.disconnect();
      window.removeEventListener("resize", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
}
