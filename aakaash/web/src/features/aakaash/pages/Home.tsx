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
        <p className="lead">Search by brand name or ingredient to see its price, cheaper brands and label text.</p>
        <MedicineSearch
          large
          autoFocus
          label="Search medicines"
          placeholder="Try “Dolo 650”, “Crocin” or an ingredient such as paracetamol"
          value={q}
          onValueChange={(v) => setParams(v ? { q: v } : {}, { replace: true })}
          onSelect={(s) => navigate(`/medicine/${s.id}`)}
        />
      </section>
      <p className="small muted hero-links">
        Taking more than one medicine? Use the <Link to="/checker">interaction checker</Link>.
      </p>
    </>
  );
}
