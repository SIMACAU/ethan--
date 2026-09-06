from pxr import Usd, UsdGeom
from pathlib import Path

paths = [
    Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\inspect\ours\item_002\item_002.usd"),
    Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\inspect\theirs\item_001\item_001.usd") if False else None,
]
# extract 001/033 if missing
import zipfile
root = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67")
z = root / "extracted" / "public_asset_baseline" / "quick_output" / "submission.zip"
dest = root / "inspect" / "theirs"
with zipfile.ZipFile(z) as archive:
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        for item in ("item_001", "item_004", "item_033", "item_034"):
            if f"/{item}/" in name and name.endswith(".usd"):
                out = dest / item / f"{item}.usd"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.read(info))

ours_z = Path(r"C:\Users\MACAU\Desktop\pack28.zip")
ours_dest = root / "inspect" / "ours"
with zipfile.ZipFile(ours_z) as archive:
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("item_002/item_002.usd"):
            out = ours_dest / "item_002" / "item_002.usd"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(info))

for p in [
    dest / "item_001" / "item_001.usd",
    dest / "item_033" / "item_033.usd",
    dest / "item_034" / "item_034.usd",
    ours_dest / "item_002" / "item_002.usd",
]:
    print(f"\n===== {p} size={p.stat().st_size} =====")
    stage = Usd.Stage.Open(str(p))
    print("upAxis", UsdGeom.GetStageUpAxis(stage), "default", stage.GetDefaultPrim())
    for prim in stage.Traverse():
        extra = ""
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            pts = mesh.GetPointsAttr().Get()
            extra = f" points={0 if pts is None else len(pts)}"
        print(f"  {prim.GetPath()} type={prim.GetTypeName()}{extra}")
