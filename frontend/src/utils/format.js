// 가격을 "29,000원" 형태로 표시한다.
export function formatPrice(price) {
  return `${price.toLocaleString("ko-KR")}원`;
}
