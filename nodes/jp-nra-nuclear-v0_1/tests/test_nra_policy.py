import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "reference" / "vsl_hive_nra_observer_reference_v0_1.py"

spec = importlib.util.spec_from_file_location("nra_observer", MODULE)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def check(text, expected_publication, reason=None):
    decision = observer.classify(text)
    assert decision["publication_candidate"] is expected_publication
    if reason is not None:
        assert decision["reason"] == reason


# Exercises must never publish.
check("訓練 原子力施設で異常を確認", False, "EXCLUDED_OR_NEGATIVE")
check("THIS IS AN EXERCISE facility impact", False, "EXCLUDED_OR_NEGATIVE")

# Explicit negative status must never publish.
check("点検の結果、異常なし", False, "EXCLUDED_OR_NEGATIVE")
check("施設への影響なし", False, "EXCLUDED_OR_NEGATIVE")

# Ambiguous / assessment-only wording must remain silent.
check("地震発生。現在、施設の状況を確認しています。", False, "NO_EXPLICIT_POSITIVE_IMPACT")

# Positive impact markers can wake only when no exclusion marker exists.
check("原子力施設で異常を確認", True, "EXPLICIT_POSITIVE_IMPACT")
check("放射性物質の漏えいを確認", True, "EXPLICIT_POSITIVE_IMPACT")
check("施設敷地緊急事態を判断", True, "EXPLICIT_POSITIVE_IMPACT")

print("NRA_POLICY_TESTS=PASS")
