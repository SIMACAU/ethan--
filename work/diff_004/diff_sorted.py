from collections import Counter

from pxr import Usd

a = Usd.Stage.Open(r"work/diff_004/p6/submission/item_004/item_004.usd")
b = Usd.Stage.Open(r"work/diff_004/pb/submission/item_004/item_004.usd")
lines_a = [line.strip() for line in a.GetRootLayer().ExportToString().splitlines()]
lines_b = [line.strip() for line in b.GetRootLayer().ExportToString().splitlines()]
counter_a, counter_b = Counter(lines_a), Counter(lines_b)
only_a = counter_a - counter_b
only_b = counter_b - counter_a
print("UNIQUE_TO_PACK6", sum(only_a.values()))
for line, count in list(only_a.items())[:20]:
    print("A", count, line[:150])
print("UNIQUE_TO_REBUILD", sum(only_b.values()))
for line, count in list(only_b.items())[:20]:
    print("B", count, line[:150])
