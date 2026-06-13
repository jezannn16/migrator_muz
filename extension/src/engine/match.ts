// Порт логики матчинга из Python core.py (доказана: 991/1012).

const FEAT = /\b(feat|ft|featuring)\b\.?.*/i;
const BRACKETS = /[([{].*?[)\]}]/g;
const NONWORD = /[^\p{L}\p{N}_\s]/gu;
const SPACES = /\s+/g;

export function normalize(s: string | null | undefined): string {
  if (!s) return "";
  let r = s.toLowerCase().trim();
  r = r.replace(FEAT, "");
  r = r.replace(BRACKETS, " ");
  r = r.replace(NONWORD, " ");
  r = r.replace(SPACES, " ").trim();
  return r;
}

// difflib.SequenceMatcher.ratio() — Ratcliff/Obershelp (Gestalt).
function longestMatch(a: string, alo: number, ahi: number, b: string, blo: number, bhi: number) {
  let bestI = alo, bestJ = blo, bestSize = 0;
  // j2len[j] = length of longest match ending at a[i-1], b[j-1]
  let j2len: Record<number, number> = {};
  for (let i = alo; i < ahi; i++) {
    const newj2len: Record<number, number> = {};
    for (let j = blo; j < bhi; j++) {
      if (a[i] === b[j]) {
        const k = (j2len[j - 1] || 0) + 1;
        newj2len[j] = k;
        if (k > bestSize) {
          bestI = i - k + 1;
          bestJ = j - k + 1;
          bestSize = k;
        }
      }
    }
    j2len = newj2len;
  }
  return { i: bestI, j: bestJ, size: bestSize };
}

function sumMatches(a: string, alo: number, ahi: number, b: string, blo: number, bhi: number): number {
  const m = longestMatch(a, alo, ahi, b, blo, bhi);
  if (m.size === 0) return 0;
  return (
    m.size +
    sumMatches(a, alo, m.i, b, blo, m.j) +
    sumMatches(a, m.i + m.size, ahi, b, m.j + m.size, bhi)
  );
}

export function ratio(a: string, b: string): number {
  const t = a.length + b.length;
  if (t === 0) return 1;
  return (2 * sumMatches(a, 0, a.length, b, 0, b.length)) / t;
}

export interface Candidate {
  videoId: string;
  title: string;
  artists: string[];
  durationSeconds?: number;
}

export function scoreCandidate(
  yaArtist: string,
  yaTitle: string,
  yaDurS: number | undefined,
  cand: Candidate,
): number {
  const t = ratio(normalize(yaTitle), normalize(cand.title));
  const a = ratio(normalize(yaArtist), normalize(cand.artists.join(" ")));
  let dur: number;
  if (cand.durationSeconds && yaDurS) {
    dur = Math.max(0, 1 - Math.abs(cand.durationSeconds - yaDurS) / 15);
  } else {
    dur = 0.5;
  }
  return 0.45 * t + 0.35 * a + 0.2 * dur;
}

export interface SearchFn {
  (query: string): Promise<Candidate[]>;
}

export async function bestMatch(
  search: SearchFn,
  yaArtist: string,
  yaTitle: string,
  yaDurS: number | undefined,
  threshold: number,
): Promise<{ cand: Candidate | null; score: number }> {
  const queries = [`${yaArtist} ${yaTitle}`, yaTitle];
  let best: Candidate | null = null;
  let bestS = 0;
  for (const q of queries) {
    for (const cand of await search(q)) {
      if (!cand.videoId) continue;
      const s = scoreCandidate(yaArtist, yaTitle, yaDurS, cand);
      if (s > bestS) {
        best = cand;
        bestS = s;
      }
    }
    if (bestS >= 0.85) break;
  }
  if (best && bestS >= threshold) return { cand: best, score: bestS };
  return { cand: null, score: bestS };
}
