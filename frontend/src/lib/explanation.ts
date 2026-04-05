export interface ExplanationResult {
  primary_reason: string;
  risk_factor: string;
  coverage_rationale: string;
}

export function buildExplanation(
  feats: Record<string, any> | null | undefined,
  score: Record<string, any> | null | undefined,
  homeTeam = "Ev sahibi",
  awayTeam = "Deplasman"
): ExplanationResult {
  if (!feats || !score) {
    return {
      primary_reason: "Veri bekleniyor.",
      risk_factor: "Analiz henüz tamamlanmadı.",
      coverage_rationale: "Kapsam hesaplanamadı.",
    };
  }

  const se = feats.strength_edge ?? 0;
  const fe = feats.form_edge ?? 0;
  const dt = feats.draw_tendency ?? 0.5;
  const vol = feats.volatility_score ?? 0.5;
  const linHome = feats.lineup_penalty_home ?? 0;
  const linAway = feats.lineup_penalty_away ?? 0;
  const primary = score.primary_pick ?? "X";
  const coverage = score.recommended_coverage ?? primary;
  const conf = score.confidence_score ?? 0;
  const covNeed = score.coverage_need_score ?? 50;
  const homeStr = (feats.home?.strength_score ?? 0) * 100;
  const awayStr = (feats.away?.strength_score ?? 0) * 100;
  const homePpg = feats.home?.season_ppg ?? 0;
  const awayPpg = feats.away?.season_ppg ?? 0;

  // ── Primary reason ────────────────────────────────────────────────────────
  let primary_reason: string;
  if (primary === "1") {
    if (se > 0.35) {
      primary_reason = `${homeTeam} güç skorunda ${homeStr.toFixed(0)}'e karşı ${awayStr.toFixed(0)} ile belirgin üstünlük sağlıyor (fark: +${(se * 100).toFixed(0)} puan).`;
    } else if (fe > 0.25) {
      primary_reason = `${homeTeam} son 5 maçtaki form eğrisinde ${awayTeam} önünde; ev avantajıyla birlikte 1 sinyali güçleniyor.`;
    } else if (homePpg > awayPpg + 0.3) {
      primary_reason = `${homeTeam} sezon genelinde maç başı ${homePpg.toFixed(2)} puan toplarken ${awayTeam} ${awayPpg.toFixed(2)}'de kalıyor.`;
    } else {
      primary_reason = `${homeTeam} ev sahibi avantajı ve hafif güç farkıyla öne çıkıyor (güven: %${conf.toFixed(0)}).`;
    }
  } else if (primary === "2") {
    if (se < -0.35) {
      primary_reason = `${awayTeam} güç skorunda ${awayStr.toFixed(0)}'e karşı ${homeStr.toFixed(0)} ile büyük üstünlük; ev sahası baskısını aşıyor.`;
    } else if (fe < -0.25) {
      primary_reason = `${awayTeam} son 5 maçtaki form eğrisinde ${homeTeam} önünde; deplasman galibiyeti sinyali güçlü.`;
    } else if (awayPpg > homePpg + 0.3) {
      primary_reason = `${awayTeam} sezon ortalaması maç başı ${awayPpg.toFixed(2)} puanla ${homeTeam}'in (${homePpg.toFixed(2)}) üzerinde seyrediyor.`;
    } else {
      primary_reason = `${awayTeam} gücü ev sahibini hafif geçiyor; deplasman galibiyeti baskın senaryo.`;
    }
  } else {
    if (dt > 0.65) {
      primary_reason = `Her iki takım çok dengeli; beraberlik eğilim skoru ${(dt * 100).toFixed(0)}/100 ile kritik eşiğin üzerinde.`;
    } else if (Math.abs(se) < 0.08 && Math.abs(fe) < 0.08) {
      primary_reason = `Güç farkı (${(se * 100).toFixed(0)}) ve form farkı (${(fe * 100).toFixed(0)}) neredeyse sıfır; X en yüksek olasılıklı senaryo.`;
    } else {
      primary_reason = `Dengeli bir maç bekleniyor; model X'i birincil seçenek olarak işaretledi (güven: %${conf.toFixed(0)}).`;
    }
  }

  // ── Risk factor ───────────────────────────────────────────────────────────
  let risk_factor: string;
  if (dt > 0.65 && primary !== "X") {
    risk_factor = `Beraberlik eğilimi yüksek (${(dt * 100).toFixed(0)}/100); öneri dışı X senaryosu göz ardı edilmemeli.`;
  } else if (linHome > 0.15 || linAway > 0.15) {
    const side = linHome > linAway ? homeTeam : awayTeam;
    const val = Math.max(linHome, linAway);
    risk_factor = `${side} kadrosunda eksik etkisi var (ceza skoru: ${(val * 100).toFixed(0)}); maç dengesi değişebilir.`;
  } else if (vol > 0.6) {
    risk_factor = `Yüksek volatilite (${(vol * 100).toFixed(0)}/100); tahmin güçlüğü ortalamanın üzerinde, sürpriz sonuç riski mevcut.`;
  } else if (conf < 22) {
    risk_factor = `Model güveni düşük (%${conf.toFixed(0)}); iki takım arasında net bir üstünlük saptanamadı, temkinli yaklaşın.`;
  } else if (Math.abs(se) < 0.05 && Math.abs(fe) < 0.05) {
    risk_factor = `Güç ve form farkları son derece küçük; maç herhangi bir sonuçla bitebilir.`;
  } else {
    risk_factor = `Belirgin ek risk faktörü saptanmadı; model sinyalleri ana öneriyle uyumlu.`;
  }

  // ── Coverage rationale ────────────────────────────────────────────────────
  let coverage_rationale: string;
  if (coverage === "1X2") {
    coverage_rationale = `Kapsam ihtiyacı kritik (${covNeed.toFixed(0)}/100); kupon riskini dağıtmak için üçlü (1X2) öneriliyor.`;
  } else if (coverage.length === 2) {
    const dir = coverage === "1X" ? "ev sahibi + beraberlik" : coverage === "X2" ? "beraberlik + deplasman" : "ev sahibi + deplasman";
    coverage_rationale = `Orta düzey kapsam ihtiyacı (${covNeed.toFixed(0)}/100); ${dir} kombinasyonuyla (${coverage}) risk yönetimi öneriliyor.`;
  } else {
    coverage_rationale = `Güçlü sinyal, kapsam ihtiyacı düşük (${covNeed.toFixed(0)}/100); tek seçenek (${coverage}) yeterli.`;
  }

  return { primary_reason, risk_factor, coverage_rationale };
}

/** Returns null-safe value with optional multiplier */
export function safeVal(v: number | null | undefined, multiply = 1): number | null {
  if (v == null || isNaN(v)) return null;
  return v * multiply;
}

/** Formats a safe value as percentage string, or returns fallback */
export function pct(v: number | null | undefined, decimals = 0): string {
  const n = safeVal(v, 100);
  if (n == null) return "—";
  return `${n.toFixed(decimals)}%`;
}

/** Formats a number or returns fallback */
export function fmt(v: number | null | undefined, decimals = 2, fallback = "—"): string {
  if (v == null || isNaN(v)) return fallback;
  return v.toFixed(decimals);
}
