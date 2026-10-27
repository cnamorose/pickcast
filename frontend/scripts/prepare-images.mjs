// 상품 사진 정리 스크립트
//
// 하는 일
//   1. 사진 폴더에서 "TOP-01.png" 처럼 상품 id 이름으로 된 사진을 찾는다.
//   2. 오른쪽 아래 생성 AI 표시 자리를 바로 왼쪽의 배경 조각으로 덮는다.
//      (사이트 하단에 "상품 이미지는 생성형 AI로 만든 이미지"라고 따로 표시한다)
//   3. 사진이 잘리지 않게 전체를 800×1000(세로 4:5) 안에 맞춰 넣고, 남는 공간은 사진 배경색으로 채워서 jpg로 frontend/public/images/<id>.jpg 로 저장한다.
//   4. src/data/products.js 의 PHOTOS 목록을 찾은 사진으로 자동으로 채운다.
//
// 사용법 (frontend 폴더에서)
//   npm install --no-save sharp
//   node scripts/prepare-images.mjs "사진 폴더 경로"

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import sharp from "sharp";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "..");
const outDir = path.join(frontend, "public", "images");
const productsFile = path.join(frontend, "src", "data", "products.js");

const srcDir = process.argv[2];
if (!srcDir || !fs.existsSync(srcDir)) {
  console.error('사진 폴더를 찾을 수 없어요. 예: node scripts/prepare-images.mjs "C:\\Users\\...\\상품사진"');
  process.exit(1);
}

// 오른쪽 아래 표시를 덮을 조각 크기 (원본 대비 비율)
const PATCH_W = 0.13;
const PATCH_H = 0.12;
const OUT_W = 800;
const OUT_H = 1000;

const ID_PATTERN = /^(TOP|BOTTOM|OUTER|DRESS|SHOES|BAG)-0[1-8]$/;
fs.mkdirSync(outDir, { recursive: true });

const done = [];
const skipped = [];

for (const file of fs.readdirSync(srcDir).sort()) {
  const ext = path.extname(file).toLowerCase();
  const id = path.basename(file, path.extname(file)).trim().toUpperCase();
  if (![".png", ".jpg", ".jpeg", ".webp"].includes(ext)) continue;
  if (!ID_PATTERN.test(id)) {
    skipped.push(file);
    continue;
  }

  const input = path.join(srcDir, file);
  const { width: W, height: H } = await sharp(input).metadata();

  // 오른쪽 아래 구석 바로 왼쪽의 배경 조각을 잘라서 구석 위에 덮는다.
  const pw = Math.round(W * PATCH_W);
  const ph = Math.round(H * PATCH_H);
  const patch = await sharp(input)
    .extract({ left: W - 2 * pw, top: H - ph, width: pw, height: ph })
    .toBuffer();

  const covered = await sharp(input)
    .composite([{ input: patch, left: W - pw, top: H - ph }])
    .toBuffer();

  // 사진 왼쪽 위 구석의 배경색을 읽어서, 비율이 달라 남는 공간을 같은 색으로 채운다.
  const { data: px } = await sharp(input)
    .extract({ left: 4, top: 4, width: 1, height: 1 })
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const background = { r: px[0], g: px[1], b: px[2] };

  await sharp(covered)
    .resize(OUT_W, OUT_H, { fit: "contain", background })
    .flatten({ background: "#ffffff" })
    .jpeg({ quality: 82, mozjpeg: true })
    .toFile(path.join(outDir, `${id}.jpg`));

  const kb = Math.round(fs.statSync(path.join(outDir, `${id}.jpg`)).size / 1024);
  console.log(`완료  ${file} → public/images/${id}.jpg (${kb}KB)`);
  done.push(`${id}.jpg`);
}

// products.js 의 PHOTOS 목록 갱신
const src = fs.readFileSync(productsFile, "utf8");
const list = done.length ? done.map((n) => `  "${n}",`).join("\n") + "\n" : "";
const updated = src.replace(/const PHOTOS = \[[\s\S]*?\];/, `const PHOTOS = [\n${list}];`);
fs.writeFileSync(productsFile, updated);

console.log(`\n사진 ${done.length}장 처리, products.js 의 PHOTOS 목록을 갱신했어요.`);
if (skipped.length) {
  console.log(`이름이 상품 id가 아니라서 건너뛴 파일: ${skipped.join(", ")}`);
}
