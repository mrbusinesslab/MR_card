import { ITEMS, CATEGORIES } from './questions.ts';

export interface ScoredCategory {
  cat: string;
  label: string;
  pct: number;
}

// answers: { [questionId: number]: number | null }（null 代表「不是我的情況」，計分時忽略）
export function scoreByCategory(answers: Record<number, number | null>): ScoredCategory[] {
  const catValues: Record<string, number[]> = {};

  for (const item of ITEMS) {
    const val = answers[item.id];
    if (val === null || val === undefined) continue;
    if (!catValues[item.cat]) catValues[item.cat] = [];
    catValues[item.cat].push(val);
  }

  const scored: ScoredCategory[] = Object.entries(catValues).map(([cat, values]) => ({
    cat,
    label: CATEGORIES[cat]?.label ?? cat,
    pct: Math.round(values.reduce((a, b) => a + b, 0) / values.length),
  }));

  scored.sort((a, b) => b.pct - a.pct);
  return scored;
}
