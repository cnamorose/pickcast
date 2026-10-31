// 점수: 맞힌 라운드의 난이도만큼 (★1 = 1점, ★2 = 2점, ★3 = 3점, 3라운드면 6점 만점)
export function points(results, who) {
  return results.reduce((sum, r) => sum + ((who === "ai" ? r.ai.correct : r.correct) ? r.level : 0), 0);
}

export function maxPoints(rounds) {
  return rounds.reduce((sum, r) => sum + r.level, 0);
}
