from pxr import Usd, UsdGeom
from pathlib import Path
import zipfile

z = Path(r"C:\Users\MACAU\Desktop\pack28.zip")
out = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\inspect\pack28\item_025")
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(z) as archive:
    for info in archive.infolist():
        if "item_025/" in info.filename.replace("\\", "/") and not info.is_dir():
            dest = out / Path(info.filename).name if info.filename.endswith(".usd") else out / "textures" / Path(info.filename).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(info))

stage = Usd.Stage.Open(str(out / "item_025.usd"))
for prim in stage.Traverse():
    print(prim.GetPath(), prim.GetTypeName())
    if prim.IsA(UsdGeom.Mesh):
        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        print("  points", list(pts) if pts else None)
        pv = UsdGeom.PrimvarsAPI(prim)
        for p in pv.GetPrimvars():
            print("  primvar", p.GetPrimvarName(), p.GetTypeName(), "count", 0 if p.Get() is None else len(p.Get()))
