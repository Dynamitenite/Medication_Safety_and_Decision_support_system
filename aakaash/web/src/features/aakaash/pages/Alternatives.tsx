import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MedicineSearch } from "../components/MedicineSearch";

/** Interim page: search for a medicine and open its alternatives view. */
export function Alternatives() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  return (
    <section className="hero">
      <h1>Alternative medicines</h1>
      <p className="lead">Choose a medicine to see other brands with the same ingredients, and the price of each.</p>
      <MedicineSearch
        large
        autoFocus
        label="Find a medicine"
        placeholder="Try “Dolo 650” or an ingredient such as paracetamol"
        value={q}
        onValueChange={setQ}
        onSelect={(s) => navigate(`/medicine/${s.id}`)}
      />
    </section>
  );
}
