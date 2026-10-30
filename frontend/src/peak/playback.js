import { useCallback, useEffect, useRef, useState } from "react";

// 사건 기록을 시간 순서대로 재생한다. time은 시뮬레이션 안의 초(1시간을 60초로 압축한 시간).
// speed 1이면 시뮬레이션 1초를 실제 1초에 보여준다.
export function usePlayback(duration, speed) {
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const last = useRef(null);

  useEffect(() => {
    if (!playing) return undefined;
    let frame;
    const step = (now) => {
      if (last.current != null) {
        const delta = ((now - last.current) / 1000) * speed;
        setTime((t) => {
          const next = Math.min(t + delta, duration);
          if (next >= duration) setPlaying(false);
          return next;
        });
      }
      last.current = now;
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      last.current = null;
    };
  }, [playing, speed, duration]);

  const play = useCallback(() => {
    setTime((t) => (t >= duration ? 0 : t));
    setPlaying(true);
  }, [duration]);
  const pause = useCallback(() => setPlaying(false), []);
  const reset = useCallback(() => {
    setPlaying(false);
    setTime(0);
  }, []);

  return { time, playing, play, pause, reset };
}

// 이 점수 미만이면 "확률 낮은 고객" (서버 평가의 low_score와 같은 기준)
export const LOW_SCORE = 1.5;

// time 시점까지의 상태: 대기 중인 요청, 누적 처리·이탈, 지킨 구매 고객, 최근 사건.
export function stateAt(replay, time) {
  if (!replay) return null;
  const waiting = new Map(); // request → arrive 사건
  const maxScore = new Map(); // 고객 → 지금까지 가장 높은 점수
  const leftUsers = new Set();
  const leftBuyers = new Set();
  const recent = [];
  let served = 0;
  let lowLeft = 0;
  const buyerLeaves = []; // 떠난 구매 고객 사건 (시간 순)
  for (const e of replay.events) {
    if (e.t > time) break;
    if (e.event === "arrive") {
      waiting.set(e.request, e);
      maxScore.set(e.user, Math.max(maxScore.get(e.user) ?? 0, e.score));
    } else if (e.event === "served") {
      waiting.delete(e.request);
      served += 1;
      recent.push(e);
    } else if (e.event === "left") {
      leftUsers.add(e.user);
      if (e.buyer) {
        leftBuyers.add(e.user);
        buyerLeaves.push(e);
      }
      if ((maxScore.get(e.user) ?? 0) < LOW_SCORE) lowLeft += 1;
      recent.push(e);
    }
  }
  // 떠난 고객의 남은 요청은 대기열에서 뺀다
  for (const [request, e] of waiting) {
    if (leftUsers.has(e.user)) waiting.delete(request);
  }
  const buyers = replay.summary.buyers;
  return {
    waiting: [...waiting.values()],
    served,
    left: leftUsers.size,
    lowLeft,
    // 아직 떠나지 않은 구매 고객. 재생이 끝나면 summary.protected_buyers와 같다.
    protectedBuyers: buyers - leftBuyers.size,
    buyers,
    buyerLeaves,
    recent: recent.slice(-10).reverse(),
  };
}

// 매초 누적 이탈을 구매 고객과 확률 낮은 고객으로 나눈다 (그래프용). 재생 전체를 한 번에 계산한다.
export function leaveTimeline(replay) {
  if (!replay) return [];
  const maxScore = new Map();
  const points = [];
  let buyerLeft = 0;
  let lowLeft = 0;
  for (const e of replay.events) {
    if (e.event === "arrive") maxScore.set(e.user, Math.max(maxScore.get(e.user) ?? 0, e.score));
    else if (e.event === "left") {
      if (e.buyer) buyerLeft += 1;
      if ((maxScore.get(e.user) ?? 0) < LOW_SCORE) lowLeft += 1;
    } else if (e.event === "tick") points.push({ t: e.t, buyerLeft, lowLeft });
  }
  return points;
}

// time 시점까지의 매초 현황 (그래프용)
export function ticksUntil(replay, time) {
  if (!replay) return [];
  return replay.events.filter((e) => e.event === "tick" && e.t <= time);
}

export function replayDuration(replay) {
  if (!replay || replay.events.length === 0) return 0;
  return replay.events[replay.events.length - 1].t;
}
