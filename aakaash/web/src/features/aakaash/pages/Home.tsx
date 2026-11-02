import { useNavigate, useSearchParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { MedicineSearch } from "../components/MedicineSearch";

/** Home: one large search box. The typed text lives in the URL (?q=) so a link reproduces the search. */
export function Home() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get("q") ?? "";
  return (
    <>
      <section className="hero">
        <h1>Find a medicine</h1>
        <p className="lead">
          Search the DailyMed prescription labels by brand name, generic name or active ingredient. Every result is a real label;
          nothing is generated.
        </p>
        <MedicineSearch
          large
          autoFocus
          label="Search medicines"
          placeholder="Try “met”, “atorvastatin” or a brand name"
          value={q}
          onValueChange={(v) => setParams(v ? { q: v } : {}, { replace: true })}
          onSelect={(s) => navigate(`/medicine/${s.set_id}`)}
        />
      </section>
      <p className="small muted hero-links">
        Checking more than one medicine? Use the <Link to="/checker">interaction checker</Link>. Dataset status is on the{" "}
        <Link to="/dashboard">dashboard</Link>.
      </p>
    </>
  );
}
