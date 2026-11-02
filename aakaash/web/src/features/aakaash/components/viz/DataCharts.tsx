import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AppmsSummaryResponse, CatalogueFormsResponse, CatalogueSummaryResponse } from "../../api";
import { ChartFrame } from "./ChartFrame";
import { LevelGlyph } from "./icons";

const plain = "rgb(var(--c-subtle))";

export function CatalogueFormsChart({ data }: { data: CatalogueFormsResponse }) {
  const rows = data.families.map(x => ({ name: x.family, products: x.products, share: data.total ? 100 * x.products / data.total : 0 }));
  return <ChartFrame title="Catalogue dosage forms" description={`Product counts by dosage-form family, from ${data.total} catalogue products.`}
    chart={<ResponsiveContainer width="100%" height={Math.max(180, rows.length * 28)}><BarChart data={rows} layout="vertical" margin={{left:8,right:18,top:4,bottom:4}} accessibilityLayer><CartesianGrid horizontal={false} stroke="rgb(var(--c-line))"/><XAxis type="number" tick={{fill:"rgb(var(--c-muted))",fontSize:12}}/><YAxis type="category" dataKey="name" width={120} tick={{fill:"rgb(var(--c-soft))",fontSize:12}}/><Tooltip/><Bar dataKey="products" name="Products" fill={plain} isAnimationActive={false}/></BarChart></ResponsiveContainer>}
    table={<table><caption>Products and share by dosage-form family</caption><thead><tr><th scope="col">Family</th><th scope="col" className="num">Products</th><th scope="col" className="num">Share</th></tr></thead><tbody>{rows.map(r=><tr key={r.name}><th scope="row">{r.name}</th><td className="num">{r.products.toLocaleString()}</td><td className="num">{r.share.toFixed(1)}%</td></tr>)}</tbody></table>}/>
}

export function CatalogueCoverageChart({ data }: { data: CatalogueSummaryResponse }) {
  const rows = [
    {name:"Products linked to a US label for every listed ingredient", value:data.brands_all_linked, total:data.brands},
    {name:"Products marked discontinued", value:data.discontinued, total:data.brands},
  ].filter(r=>r.total > 0).map(r=>({...r, share:100*r.value/r.total}));
  return <ChartFrame title="Catalogue coverage" description="Share of catalogue products linked to labels for every listed ingredient and share marked discontinued. Each row uses the stated catalogue total."
    chart={<ResponsiveContainer width="100%" height={Math.max(150,rows.length*48)}><BarChart data={rows} layout="vertical" margin={{left:8,right:24,top:4,bottom:4}} accessibilityLayer><CartesianGrid horizontal={false} stroke="rgb(var(--c-line))"/><XAxis type="number" domain={[0,100]} unit="%" tick={{fill:"rgb(var(--c-muted))",fontSize:12}}/><YAxis type="category" dataKey="name" width={260} tick={{fill:"rgb(var(--c-soft))",fontSize:12}}/><Tooltip formatter={(v:number)=>`${v.toFixed(1)}%`}/><Bar dataKey="share" name="Share" fill={plain} isAnimationActive={false}/></BarChart></ResponsiveContainer>}
    table={<table><caption>Catalogue coverage counts and shares</caption><thead><tr><th scope="col">Measure</th><th scope="col" className="num">Count</th><th scope="col" className="num">Total products</th><th scope="col" className="num">Share</th></tr></thead><tbody>{rows.map(r=><tr key={r.name}><th scope="row">{r.name}</th><td className="num">{r.value.toLocaleString()}</td><td className="num">{r.total.toLocaleString()}</td><td className="num">{r.share.toFixed(1)}%</td></tr>)}</tbody></table>}/>
}

export function RuleSeverityChart({ data }: { data: AppmsSummaryResponse }) {
  const rows = data.severity.map(x=>({name:x.severity,count:x.scenarios}));
  const level = (name: string) => name === "Moderate" ? "Medium" as const : name as "High" | "Critical";
  return <ChartFrame title="Rule severity counts" description="Scenario counts by severity in the loaded rules dataset. These are dataset counts, not patient risk estimates."
    chart={<><ResponsiveContainer width="100%" height={Math.max(150, rows.length*42)}><BarChart data={rows} layout="vertical" margin={{left:8,right:24,top:4,bottom:4}} accessibilityLayer><CartesianGrid horizontal={false} stroke="rgb(var(--c-line))"/><XAxis type="number" tick={{fill:"rgb(var(--c-muted))",fontSize:12}}/><YAxis type="category" dataKey="name" width={100} tick={{fill:"rgb(var(--c-soft))",fontSize:12}}/><Tooltip/><Bar dataKey="count" name="Scenarios" isAnimationActive={false}>{rows.map(r=><Cell key={r.name} fill={r.name === "Critical" || r.name === "High" ? "rgb(var(--c-rose))" : r.name === "Moderate" ? "rgb(var(--c-amber))" : plain}/>)}</Bar></BarChart></ResponsiveContainer><ul className="severity-key small" aria-label="Severity key">{rows.map(r=><li key={r.name}><LevelGlyph level={level(r.name)} size={15}/>{r.name}{r.name === "Moderate" ? " (shown as Medium in the app)" : ""}</li>)}</ul></>}
    table={<table><caption>Scenario counts by rule severity</caption><thead><tr><th scope="col">Severity</th><th scope="col" className="num">Scenarios</th></tr></thead><tbody>{rows.map(r=><tr key={r.name}><th scope="row"><span className="severity-label"><LevelGlyph level={level(r.name)} size={15}/>{r.name}</span></th><td className="num">{r.count.toLocaleString()}</td></tr>)}</tbody></table>}/>
}
