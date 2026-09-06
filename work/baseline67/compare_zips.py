import hashlib
import zipfile
from pathlib import Path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def members(p: Path) -> dict[str, int]:
    with zipfile.ZipFile(p) as z:
        return {i.filename: i.file_size for i in z.infolist() if not i.is_dir()}


def item_key(name: str) -> str | None:
    for part in name.replace("\\", "/").split("/"):
        if part.startswith("item_"):
            return part
    return None


def by_item(m: dict[str, int]) -> dict[str, list[tuple[str, int]]]:
    d: dict[str, list[tuple[str, int]]] = {}
    for n, s in m.items():
        k = item_key(n)
        if k:
            d.setdefault(k, []).append((n, s))
    return d


root = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\extracted\public_asset_baseline")
files = {
    "quick": root / "quick_output" / "submission.zip",
    "ref": root / "artifacts" / "reference" / "submission.zip",
    "base": root / "artifacts" / "intermediate" / "base_submission.zip",
    "donor": root / "artifacts" / "intermediate" / "donor_submission.zip",
    "ours": Path(r"C:\Users\MACAU\Desktop\pack28.zip"),
}

print("=== hashes ===")
for k, p in files.items():
    print(f"{k:6} size={p.stat().st_size:10d} md5={md5(p)} sha256={sha256(p)}")

print("\n=== member counts ===")
for k, p in files.items():
    print(f"{k:6} n={len(members(p))}")

q = members(files["quick"])
o = members(files["ours"])
d = members(files["donor"])
b = members(files["base"])
print("\nours sample:", list(o)[:8])
print("theirs sample:", list(q)[:8])

qi, oi = by_item(q), by_item(o)
print("\nitem | ours_n ours_bytes | theirs_n theirs_bytes | theirs_files")
for i in range(1, 35):
    k = f"item_{i:03d}"
    oa = oi.get(k, [])
    ta = qi.get(k, [])
    names = [n.split("/")[-1] for n, _ in ta]
    print(
        f"{k} | {len(oa):2d} {sum(s for _, s in oa):8d} | {len(ta):2d} {sum(s for _, s in ta):8d} | {names}"
    )

print("\n=== non-usd theirs ===")
for n, s in sorted(q.items()):
    if not n.endswith(".usd"):
        print(f"{s:10d} {n}")

print("\n=== non-usd ours ===")
for n, s in sorted(o.items()):
    if not n.endswith(".usd"):
        print(f"{s:10d} {n}")

print("\n=== donor vs base vs final for 029/030 ===")
for task in ("item_029", "item_030", "item_002"):
    for label, m in (("base", b), ("donor", d), ("final", q), ("ours", o)):
        hits = [(n, s) for n, s in m.items() if f"/{task}/" in n.replace("\\", "/")]
        print(f"{task} {label:5} {[(n.split('/')[-1], s) for n, s in hits]}")
