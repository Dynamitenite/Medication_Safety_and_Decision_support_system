// SOURCE: WHO adult BMI classification (underweight below 18.5, normal 18.5 to 24.9, overweight 25 to 29.9,
// obese 30 and over). Pure logic: no React, so `npm test` can run it.
export const BMI_SOURCE = "WHO adult BMI classification, for adults aged 18 and over";

export type BmiBand = { id: "underweight" | "normal" | "overweight" | "obese"; label: string; from: number; to: number | null; range: string };

export const BMI_BANDS: BmiBand[] = [
  { id: "underweight", label: "Underweight", from: 0, to: 18.5, range: "below 18.5" },
  { id: "normal", label: "Normal range", from: 18.5, to: 25, range: "18.5 to 24.9" },
  { id: "overweight", label: "Overweight", from: 25, to: 30, range: "25 to 29.9" },
  { id: "obese", label: "Obese", from: 30, to: null, range: "30 and over" },
];

/** The part of the BMI axis that is drawn; a value outside it sits on the edge and the number is still printed. */
export const BMI_AXIS = { min: 15, max: 40 };

export function bmiBand(bmi: number): BmiBand {
  return BMI_BANDS.find((b) => b.to === null || bmi < b.to) ?? BMI_BANDS[BMI_BANDS.length - 1];
}

export type BmiScale = { show: true; bmi: number; band: BmiBand; position: number } | { show: false; reason: string };

/** The scale is shown only for age 18 and over with a BMI. Otherwise `reason` says why it is hidden. */
export function bmiScale(age: number | null | undefined, bmi: number | null | undefined): BmiScale {
  if (age == null) return { show: false, reason: "The BMI scale is hidden because no date of birth is entered. The WHO ranges apply to adults aged 18 and over." };
  if (age < 18) return { show: false, reason: "The BMI scale is hidden because the WHO adult ranges apply from age 18. Ask a doctor how to read BMI for a child or teenager." };
  if (bmi == null) return { show: false, reason: "Enter height and weight to see the BMI scale." };
  const position = Math.min(1, Math.max(0, (bmi - BMI_AXIS.min) / (BMI_AXIS.max - BMI_AXIS.min)));
  return { show: true, bmi, band: bmiBand(bmi), position };
}
