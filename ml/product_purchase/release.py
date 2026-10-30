"""서비스 모델 버전 관리. ml/models/ 아래 버전 폴더 중 서비스가 쓸 버전을 current.json으로 정한다.

    ml/models/
      current.json              {"version": "product_purchase_v1"}
      product_purchase_v1/      calibration.json, 모델 파일, metadata.json
      product_purchase_v2/

버전 폴더는 덮어쓰지 않고 새로 만든다. 반영과 되돌리기는 current.json만 바꾼다.
백엔드는 몇 초마다 current.json을 확인해 재시작 없이 새 버전을 불러온다 (backend/app/ml.py).

    python ml/product_purchase/release.py list       # 버전 목록과 지금 쓰는 버전
    python ml/product_purchase/release.py use v2     # v2로 반영 (product_purchase_v2와 같음)
    python ml/product_purchase/release.py use v1     # 되돌리기
"""
import argparse
import json
import re
import shutil
from pathlib import Path

from events import ml_dir

MODELS_DIR = ml_dir / "models"
CURRENT_FILE = "current.json"
VERSION_PREFIX = "product_purchase_"


def normalize(version):
    """v2처럼 짧게 써도 product_purchase_v2로 받는다."""
    return version if version.startswith(VERSION_PREFIX) else VERSION_PREFIX + version


def current_version(models_dir=MODELS_DIR):
    return json.loads((Path(models_dir) / CURRENT_FILE).read_text(encoding="utf-8"))["version"]


def release_dir(version=None, models_dir=MODELS_DIR):
    """버전 폴더 경로. version이 없으면 current.json이 가리키는 버전."""
    return Path(models_dir) / normalize(version or current_version(models_dir))


def check_version(directory):
    """서비스에 쓸 수 있는 버전 폴더인지 확인한다. 문제가 있으면 이유를 돌려준다."""
    calibration_path = directory / "calibration.json"
    if not directory.is_dir():
        return f"폴더가 없습니다: {directory}"
    if not calibration_path.exists():
        return f"calibration.json이 없습니다: {directory}"
    model = json.loads(calibration_path.read_text(encoding="utf-8")).get("model")
    if not model or not (directory / f"{model}.txt").exists():
        return f"calibration.json에 적힌 모델 파일({model}.txt)이 없습니다: {directory}"
    return None


def list_versions(models_dir=MODELS_DIR):
    """버전 폴더 목록. 각 버전의 metadata.json 설명과 사용 가능 여부를 함께 돌려준다."""
    versions = []
    for directory in sorted(Path(models_dir).glob(f"{VERSION_PREFIX}*")):
        metadata_path = directory / "metadata.json"
        metadata = (
            json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        )
        versions.append(
            {
                "version": directory.name,
                "created": metadata.get("created"),
                "description": metadata.get("description"),
                "problem": check_version(directory),
            }
        )
    return versions


def next_version(models_dir=MODELS_DIR):
    """다음 버전 이름. product_purchase_v2까지 있으면 product_purchase_v3."""
    numbers = [
        int(match.group(1))
        for directory in Path(models_dir).glob(f"{VERSION_PREFIX}v*")
        if (match := re.fullmatch(rf"{VERSION_PREFIX}v(\d+)", directory.name))
    ]
    return f"{VERSION_PREFIX}v{max(numbers, default=0) + 1}"


def register_version(version, base_version, calibration, threshold, metadata, models_dir=MODELS_DIR):
    """기존 버전의 모델 파일에 새 보정을 붙여 새 버전 폴더를 만든다. 이미 있으면 덮어쓰지 않는다.

    서비스 반영(current.json)은 하지 않는다. 반영은 use_version으로 따로 한다.
    """
    directory = Path(models_dir) / normalize(version)
    if directory.exists():
        raise FileExistsError(f"이미 있는 버전입니다: {directory}")
    base_dir = release_dir(base_version, models_dir)
    model = json.loads((base_dir / "calibration.json").read_text(encoding="utf-8"))["model"]
    directory.mkdir()
    shutil.copy(base_dir / f"{model}.txt", directory)
    (directory / "calibration.json").write_text(
        json.dumps({"model": model, **calibration, "threshold": threshold}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (directory / "metadata.json").write_text(
        json.dumps({"version": directory.name, **metadata}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return directory


def use_version(version, models_dir=MODELS_DIR):
    """서비스가 쓸 버전을 바꾼다. 쓸 수 없는 폴더면 바꾸지 않는다."""
    version = normalize(version)
    problem = check_version(Path(models_dir) / version)
    if problem:
        raise ValueError(problem)
    (Path(models_dir) / CURRENT_FILE).write_text(
        json.dumps({"version": version}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return version


def main():
    parser = argparse.ArgumentParser(description="서비스 모델 버전 관리")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="버전 목록과 지금 쓰는 버전")
    use = commands.add_parser("use", help="서비스가 쓸 버전을 바꾼다 (반영·되돌리기)")
    use.add_argument("version", help="예: v2 또는 product_purchase_v2")
    args = parser.parse_args()

    if args.command == "list":
        current = current_version()
        for v in list_versions():
            mark = "*" if v["version"] == current else " "
            status = f"  [사용 불가: {v['problem']}]" if v["problem"] else ""
            print(f"{mark} {v['version']}  {v['created'] or '-'}  {v['description'] or ''}{status}")
        print("\n* 지금 서비스가 쓰는 버전")
    else:
        previous = current_version()
        try:
            version = use_version(args.version)
        except ValueError as error:
            raise SystemExit(f"바꾸지 않았습니다. {error}")
        print(f"{previous} → {version}")
        print("실행 중인 백엔드는 몇 초 안에 새 버전을 씁니다 (/health의 model_version으로 확인).")


if __name__ == "__main__":
    main()
