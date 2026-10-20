from __future__ import annotations
import json
from pathlib import Path
CONFIG_PATH = Path(__file__).resolve().parent / "tests_config.json"
def load_tests() -> dict[int, dict[str, object]]:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {int(item["id"]): item for item in data}
def get_test(test_id: int) -> dict[str, object]:
    tests = load_tests()
    if test_id not in tests:
        raise RuntimeError(f"Тест з ID {test_id} не знайдено в tests_config.json")
    test = tests[test_id]
    url = str(test.get("url", "")).strip()
    if not url:
        raise RuntimeError(f"Для Тесту {test_id} ще не задано URL Moodle. Відкрий tests_config.json і впиши URL у поле url.")
    return test
