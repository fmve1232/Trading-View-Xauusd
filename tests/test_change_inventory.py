"""audit/tools/change_inventory.py: functions and methods are found by their syntax tree and compared by source."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import change_inventory as C


def test_functions_and_methods_by_qualified_name():
    src = "def a():\n    return 1\n\n\nclass K:\n    def m(self):\n        def inner():\n            pass\n        return inner\n"
    f = C.functions(src)
    assert set(f) == {"a", "K.m", "K.m.inner"} and f["a"].startswith("def a")
    assert C.functions(None) == {} and C.functions("def broken(:\n") == {}
    changed = C.functions(src.replace("return 1", "return 2"))
    assert [n for n in f if f[n] != changed[n]] == ["a"]
