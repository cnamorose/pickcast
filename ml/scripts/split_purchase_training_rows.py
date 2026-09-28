import csv
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path


ml_dir = Path(__file__).resolve().parents[1]
source = ml_dir / "data" / "processed" / "product_purchase_v2" / "training_rows.csv"
output_dir = source.parent / "splits"
output_dir.mkdir(parents=True, exist_ok=True)

names = ("train", "valid", "calibration", "test")
cutoffs = []
previous_key = None

# 상품 행이 아니라 예측 시점의 시간 분포로 경계를 정합니다.
with source.open(newline="", encoding="utf-8") as file:
    reader = csv.DictReader(file)
    for row in reader:
        key = (row["visitorid"], row["cutoff_timestamp"])
        if key != previous_key:
            cutoffs.append(int(row["cutoff_timestamp"]))
            previous_key = key

cutoffs.sort()
valid_start = cutoffs[int(len(cutoffs) * 0.65)]
calibration_start = cutoffs[int(len(cutoffs) * 0.80)]
test_start = cutoffs[int(len(cutoffs) * 0.90)]

stats = defaultdict(Counter)
temp_paths = {
    name: output_dir / f"{name}.csv.tmp"
    for name in (*names, "excluded")
}

with ExitStack() as stack:
    input_file = stack.enter_context(source.open(newline="", encoding="utf-8"))
    reader = csv.DictReader(input_file)

    writers = {}
    for name, path in temp_paths.items():
        file = stack.enter_context(path.open("w", newline="", encoding="utf-8"))
        writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
        writer.writeheader()
        writers[name] = writer

    previous_key = None

    for row in reader:
        cutoff = int(row["cutoff_timestamp"])
        label_end = int(row["label_end_timestamp"])

        if cutoff < valid_start:
            name = "train" if label_end < valid_start else "excluded"
        elif cutoff < calibration_start:
            name = "valid" if label_end < calibration_start else "excluded"
        elif cutoff < test_start:
            name = "calibration" if label_end < test_start else "excluded"
        else:
            name = "test"

        writers[name].writerow(row)
        stats[name]["rows"] += 1
        stats[name]["positive_rows"] += int(row["label"])

        key = (row["visitorid"], row["cutoff_timestamp"])
        if key != previous_key:
            stats[name]["snapshots"] += 1
            previous_key = key

for name, temp_path in temp_paths.items():
    temp_path.replace(output_dir / f"{name}.csv")


def utc_time(timestamp_ms):
    return datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat(timespec="milliseconds")


report = {
    "valid_start_ms": valid_start,
    "calibration_start_ms": calibration_start,
    "test_start_ms": test_start,
    "valid_start_utc": utc_time(valid_start),
    "calibration_start_utc": utc_time(calibration_start),
    "test_start_utc": utc_time(test_start),
    "splits": {name: dict(stats[name]) for name in temp_paths},
}
(output_dir / "split_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

for label, timestamp in [
    ("검증 시작", valid_start),
    ("확률 보정 시작", calibration_start),
    ("최종 평가 시작", test_start),
]:
    print(f"{label}: {utc_time(timestamp)}")

print("\n=== 분리 결과 ===")
for name in temp_paths:
    result = stats[name]
    print(
        f"{name}: 예측 시점 {result['snapshots']:,}개 / "
        f"상품 행 {result['rows']:,}개 / "
        f"구매 정답 {result['positive_rows']:,}행"
    )
print(f"\n저장 위치: {output_dir}")
