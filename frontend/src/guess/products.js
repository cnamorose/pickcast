import { CATEGORY_LABELS, PRODUCTS } from "../data/products";

// 실제 데이터의 상품은 번호뿐이라, 게임마다 쇼핑몰 상품을 무작위로 붙여 보여준다.
// 한 게임 안에서는 같은 번호에 같은 상품이 붙고, 서로 다른 번호에는 다른 상품이 붙는다.
// (한 게임의 상품 번호는 최대 18개, 쇼핑몰 상품은 48개)
export function assignProducts(rounds) {
  const pool = [...PRODUCTS];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  const productOf = {};
  for (const round of rounds) {
    for (const item of round.items) {
      if (!(item in productOf)) productOf[item] = pool[Object.keys(productOf).length];
    }
  }
  return productOf;
}

// 쇼핑몰 카드와 같은 방식(카테고리 + 상품 번호)으로 이름을 붙인다.
export function productLabel(product) {
  return `${CATEGORY_LABELS[product.category]} ${product.id}`;
}
