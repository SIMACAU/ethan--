import zipfile
from pathlib import Path
from pxr import Usd, UsdGeom, UsdPhysics

ROOT = Path(r"C:\Users\MACAU\Desktop\天池")
OUT = ROOT / "work" / "baseline67" / "inspect" / "pack28"
OUT.mkdir(parents=True, exist_ok=True)
Z = Path(r"C:\Users\MACAU\Desktop\pack28.zip")
ITEMS = ("item_002", "item_018", "item_019", "item_022", "item_025", "item_026", "item_029", "item_030")

with zipfile.ZipFile(Z) as z:
    for info in z.infolist():
        name = info.filename.replace("\\", "/")
        for item in ITEMS:
            if f"/{item}/" in name and not info.is_dir():
                rel = Path(*Path(name).parts[Path(name).parts.index(item) :])
                dest = OUT / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(info))

for item in ITEMS:
    usd = OUT / item / f"{item}.usd"
    print(f"\n===== {item} size={usd.stat().st_size} =====")
    stage = Usd.Stage.Open(str(usd))
    print("up", UsdGeom.GetStageUpAxis(stage), "mpu", UsdGeom.GetStageMetersPerUnit(stage), "default", stage.GetDefaultPrim())
    for prim in stage.Traverse():
        extra = ""
        if prim.IsA(UsdGeom.Mesh):
            pts = UsdGeom.Mesh(prim).GetPointsAttr().Get()
            extra += f" pts={0 if pts is None else len(pts)}"
        if prim.IsA(UsdGeom.Xformable):
            xf = UsdGeom.Xformable(prim)
            ops = xf.GetOrderedXformOps()
            if ops:
                extra += " xf=" + ",".join(op.GetOpType().displayName + "=" + str(op.Get()) for op in ops)
        schemas = prim.GetAppliedSchemas()
        if schemas:
            extra += " api=" + ",".join(str(s) for s in schemas)
        if prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint):
            extra += " JOINT"
        print(f"  {prim.GetPath()} {prim.GetTypeName()}{extra}")
    tex = list((OUT / item / "textures").glob("*")) if (OUT / item / "textures").exists() else []
    print("textures", [(p.name, p.stat().st_size) for p in tex])
