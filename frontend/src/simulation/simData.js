// 시뮬레이션 화면에서 쓰는 계산·문구 함수. 화면 코드와 나눠 둔다.
// 처음 보는 사람도 읽을 수 있게 피처 이름 대신 쉬운 문장으로 바꾼다.
import { CATEGORY_LABELS, PRODUCTS } from "../data/products";

// 마지막 행동 뒤 이만큼(초) 지나면 손님이 나간 것으로 보여준다.
export const LINGER_SECONDS = 90;

// 실제 데이터의 상품은 번호뿐이라 쇼핑몰 상품(48개) 그림을 붙인다.
// - 탭 손님들이 본 상품은 처음 나온 순서대로 서로 다른 그림을 붙인다 (assignFeatured).
// - 나머지 상품은 상품 번호로 정해, 남은 그림 중 하나를 붙인다. 가게 전체 상품이 48개보다 많아 서로 겹칠 수 있다.
// 손님 화면과 판매자 화면에서 같은 상품은 늘 같은 그림이다.
// 카테고리 순서로 붙지 않게 고정된 순서로 섞어 둔다.
const SHUFFLED = [...PRODUCTS].sort((a, b) => hashText(a.id) - hashText(b.id));
let featured = new Map();
let rest = SHUFFLED;

function hashText(text) {
  let h = 2166136261;
  for (const ch of text) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return h;
}

export function assignFeatured(itemIds) {
  featured = new Map();
  for (const item of itemIds) {
    if (!featured.has(item) && featured.size < SHUFFLED.length) featured.set(item, SHUFFLED[featured.size]);
  }
  const used = new Set([...featured.values()].map((p) => p.id));
  const left = SHUFFLED.filter((p) => !used.has(p.id));
  rest = left.length > 0 ? left : SHUFFLED;
}

export function productFor(item) {
  if (featured.has(item)) return featured.get(item);
  const mixed = (Number(item) * 2654435761) % 4294967296;
  return rest[mixed % rest.length];
}

// "코듀로이 팬츠(브라운)"
export function productName(item) {
  const product = productFor(item);
  return `${product.type}(${product.color})`;
}

export function categoryName(item) {
  return CATEGORY_LABELS[productFor(item).category];
}

// 상품 이름 뒤 조사(을/를, 이/가, 은/는). 괄호 앞 종류 이름의 마지막 글자 받침으로 고른다.
export function withParticle(item, pair) {
  const last = productFor(item).type.trim().slice(-1);
  const code = last.charCodeAt(0) - 0xac00;
  const hasFinal = code >= 0 && code < 11172 && code % 28 !== 0;
  const [consonant, vowel] = { 을: ["을", "를"], 이: ["이", "가"], 은: ["은", "는"] }[pair];
  return `${productName(item)}${hasFinal ? consonant : vowel}`;
}

// "손님 2가", "손님 3이": 숫자를 읽은 소리(일·이·삼…)의 받침으로 조사를 고른다.
export function customerSubject(id) {
  const particle = { 0: "이", 1: "이", 2: "가", 3: "이", 4: "가", 5: "가", 6: "이", 7: "이", 8: "이", 9: "가" }[id % 10];
  return `손님 ${id}${particle}`;
}

// "손님 2는", "손님 3은"
export function customerTopic(id) {
  const particle = { 0: "은", 1: "은", 2: "는", 3: "은", 4: "는", 5: "는", 6: "은", 7: "은", 8: "은", 9: "는" }[id % 10];
  return `손님 ${id}${particle}`;
}

export function durationText(seconds) {
  if (seconds == null) return "-";
  const s = Math.round(seconds);
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  if (m < 60) return rest ? `${m}분 ${rest}초` : `${m}분`;
  return `${Math.floor(m / 60)}시간 ${m % 60}분`;
}

export function percent(value, digits = 1) {
  if (value == null) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

// 시간 창 시작부터 지난 초 → "17:42"
export function clockText(window, seconds) {
  const minute = window.start_minute + Math.floor(seconds / 60);
  return `${String(Math.floor(minute / 60) % 24).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

// 모델 판정(임계값 이상이면 "구매 예상")을 쉬운 말로
export function verdict(decision) {
  return decision === "구매 예상" ? "살 것 같아요" : "아직 몰라요";
}

const RECENT_SECONDS = 120;

// 이유 하나를 쉬운 문장으로. up이 참이면 살 가능성을 높인 이유다. 값이 없는 피처는 null.
export function reasonSentence({ feature, value, contribution }) {
  const up = contribution >= 0;
  if (value == null) return null;
  const sentences = {
    seconds_since_last_cart: () => (value <= RECENT_SECONDS ? "방금 장바구니에 담았어요" : `장바구니에 담은 지 ${durationText(value)} 지났어요`),
    cart_count: () => (value > 0 ? `장바구니에 ${value}번 담았어요` : "이 상품은 아직 장바구니에 없어요"),
    user_carted_items: () => (value > 0 ? `장바구니에 담은 상품이 ${value}개 있어요` : "아직 아무것도 담지 않았어요"),
    seconds_since_last_view: () => (value <= RECENT_SECONDS ? "방금 이 상품을 봤어요" : `이 상품을 본 지 ${durationText(value)} 지났어요`),
    seconds_since_first_view: () => `이 상품을 처음 본 지 ${durationText(value)} 지났어요`,
    view_count: () => `이 상품을 ${value}번 봤어요`,
    revisit_count: () => (value > 0 ? `다른 상품을 보다가 ${value}번 다시 돌아왔어요` : "다시 돌아와서 본 적은 없어요"),
    view_share: () => `본 것 중 ${percent(value, 0)}가 이 상품이에요`,
    user_total_views: () => `지금까지 ${value}번 둘러봤어요`,
    distinct_items_viewed: () => `상품 ${value}개를 비교하고 있어요`,
    is_last_viewed: () => (value ? "가장 최근에 본 상품이에요" : "지금은 다른 상품을 보고 있어요"),
    item_viewers: () => `평소 ${Math.round(value).toLocaleString()}명이 본 상품이에요`,
    item_purchase_rate: () => (up ? `평소 잘 팔리는 상품이에요` : `평소 잘 안 팔리는 상품이에요`),
    item_cart_rate: () => (up ? `평소 장바구니에 자주 담기는 상품이에요` : `평소 장바구니에 잘 안 담기는 상품이에요`),
  };
  const make = sentences[feature];
  return make ? { text: make(), up } : null;
}

// 손님 한 명의 지금(t초) 상태: 아직 안 옴 / 쇼핑 중 / 나감
export function customerState(journey, t) {
  const steps = journey.steps;
  if (t < steps[0].second) return { status: "waiting", enterIn: steps[0].second - t };
  let index = 0;
  while (index + 1 < steps.length && steps[index + 1].second <= t) index += 1;
  const step = steps[index];
  const last = index === steps.length - 1;
  if (last && t > step.second + LINGER_SECONDS) return { status: "left", index };
  const span = step.dwell_seconds ?? LINGER_SECONDS;
  return { status: "shopping", index, progress: Math.min(1, (t - step.second) / span) };
}

// 가운데 자막: 손님이 한 일과, 그때 AI 예측이 어떻게 바뀌었는지 한 줄씩.
export function narrate(journey, index) {
  const current = journey.steps[index];
  const item = current.item_id;
  const previous = index > 0 ? journey.steps[index - 1].dashboard.candidates : [];
  const before = previous.find((c) => c.item_id === item);
  const now = current.dashboard.candidates.find((c) => c.item_id === item);
  const revisit = journey.steps.slice(0, index).some((s) => s.item_id === item);
  const sameAsPrevious = index > 0 && journey.steps[index - 1].item_id === item;

  if (current.event === "transaction") {
    return {
      icon: "💳",
      customer: `${customerSubject(journey.id)} ${withParticle(item, "을")} 샀어요!`,
      ai: before
        ? `AI는 구매 직전 이 상품을 ${before.rank}순위로 보고 있었어요 (살 가능성 ${percent(before.probability)})`
        : "AI가 미리 보지 못한 상품이에요",
      key: true,
    };
  }
  let customer;
  if (current.event === "addtocart") customer = `${customerSubject(journey.id)} ${withParticle(item, "을")} 장바구니에 담았어요`;
  else if (sameAsPrevious) customer = `${customerSubject(journey.id)} ${withParticle(item, "을")} 계속 보고 있어요`;
  else if (revisit) customer = `${customerSubject(journey.id)} ${withParticle(item, "을")} 다시 보러 왔어요`;
  else customer = `${customerSubject(journey.id)} ${withParticle(item, "을")} 보고 있어요`;

  const likely = now && now.decision === "구매 예상" && now.rank === 1;
  const wasLikely = before && before.decision === "구매 예상" && before.rank === 1;
  let ai;
  if (!now) ai = "AI: 이 상품은 이미 샀어요";
  else if (index === 0) ai = "AI가 이 손님을 지켜보기 시작했어요. 아직은 둘러보는 중이에요";
  else if (likely && wasLikely) ai = now.probability < before.probability * 0.85 ? `AI: "여전히 살 것 같지만, 조금 낮아졌어요"` : `AI: "여전히 살 것 같아요"`;
  else if (likely) ai = `AI: "이 상품을 살 것 같아요!"`;
  else if (before && now.probability > before.probability * 1.3) ai = "AI: 이 상품에 관심이 커지고 있어요";
  else if (before && now.probability < before.probability * 0.77) ai = "AI: 이 상품에 대한 관심이 줄었어요";
  else if (!before) ai = "AI: 관심 상품이 하나 늘었어요. 아직은 둘러보는 중이에요";
  else ai = "AI: 아직은 둘러보는 중이에요";
  return {
    icon: current.event === "addtocart" ? "🛒" : "👀",
    customer,
    ai,
    from: before?.probability,
    to: now?.probability,
    key: current.event === "addtocart",
  };
}

// 손님이 나간 뒤 보여줄 결과 문구
export function outcomeLines(journey, threshold) {
  const last = journey.steps[journey.steps.length - 1].dashboard;
  if (journey.outcomes.length === 0) {
    const top = last.candidates[0];
    if (top && top.decision === "구매 예상") {
      return [{
        tone: "miss",
        title: "AI가 틀렸어요: 사지 않고 나갔어요",
        text: `AI는 ${withParticle(top.item_id, "을")} "살 것 같아요"(${percent(top.probability)})라고 봤지만 사지 않았어요. 담고도 안 사는 손님도 많아요.`,
      }];
    }
    return [{ tone: "neutral", title: "사지 않고 나갔어요", text: "AI도 살 것 같다고 보지 않았어요." }];
  }
  return journey.outcomes.map((o) => {
    if (o.top1_seconds_before != null) {
      // 구매 바로 앞 행동 직후의 후보 수. 하나뿐이면 1순위는 당연하므로 맞혔다고 하지 않는다.
      const before = journey.steps.filter((s) => s.second < o.second && s.event !== "transaction").at(-1);
      const candidates = before ? before.dashboard.candidates.length : 0;
      if (candidates <= 1) {
        return {
          tone: "neutral",
          title: "본 상품을 그대로 샀어요",
          text: `본 상품이 하나뿐이라 AI의 1순위도 그 상품이었어요 (살 가능성 ${percent(o.probability_before)}${
            o.probability_before < threshold ? `, "살 것 같아요" 기준 ${percent(threshold)} 미만` : ""
          }).`,
        };
      }
      return {
        tone: "hit",
        title: "AI가 맞혔어요!",
        text: `관심 상품 ${candidates}개 중 ${withParticle(o.item_id, "을")} 구매 ${durationText(o.top1_seconds_before)} 전부터 1순위로 꼽았어요. 판매자는 그만큼 먼저 알 수 있어요.`,
      };
    }
    return {
      tone: "miss",
      title: "AI가 놓쳤어요",
      text: o.rank_before
        ? `${withParticle(o.item_id, "은")} 구매 직전 ${o.rank_before}순위였어요 (살 가능성 ${percent(o.probability_before)}).`
        : "AI가 미리 보지 못한 상품이에요.",
    };
  });
}

// 손님 화면 위 장바구니 개수: 지금까지 담았고 아직 사지 않은 상품 수
export function cartCount(journey, index) {
  const carted = new Set();
  for (const step of journey.steps.slice(0, index + 1)) {
    if (step.event === "addtocart") carted.add(step.item_id);
    if (step.event === "transaction") carted.delete(step.item_id);
  }
  return carted.size;
}
