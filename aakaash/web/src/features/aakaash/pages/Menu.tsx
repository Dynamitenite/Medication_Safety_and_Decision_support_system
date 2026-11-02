import { Link, Navigate, useSearchParams } from "react-router-dom";
import { MENU } from "../registry";
import { MENU_ICONS } from "./MenuIcons";

/** The signed-in start page: the four options as large tiles. */
export function Menu() {
  const [params] = useSearchParams();
  // the search page used to live at "/": keep old links such as /?q=paracetamol working
  if (params.has("q")) return <Navigate to={`/search?${params}`} replace />;
  return (
    <>
      <h1>What would you like to do?</h1>
      <ul className="tiles">
        {MENU.map((m) => {
          const Glyph = MENU_ICONS[m.id];
          return (
            <li key={m.id}>
              <Link to={m.path} className="tile">
                <Glyph size={28} aria-hidden="true" />
                <span className="tile-title">{m.label}</span>
                <span className="small muted">{m.blurb}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}
