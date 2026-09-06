import difflib

from pxr import Usd

a = Usd.Stage.Open(r"work/diff_004/p6/submission/item_004/item_004.usd")
b = Usd.Stage.Open(r"work/diff_004/pb/submission/item_004/item_004.usd")
lines_a = a.GetRootLayer().ExportToString().splitlines()
lines_b = b.GetRootLayer().ExportToString().splitlines()
diff = list(difflib.unified_diff(lines_a, lines_b, lineterm="", n=1))
print("DIFF_LINES", len(diff))
print("\n".join(diff[:80]))
