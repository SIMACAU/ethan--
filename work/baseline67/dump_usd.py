import zipfile
from pathlib import Path
from pxr import Usd, UsdGeom

ROOT = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67")
OUT = ROOT / "inspect"
OUT.mkdir(parents=True, exist_ok=True)

zips = {
    "theirs": ROOT / "extracted" / "public_asset_baseline" / "quick_output" / "submission.zip",
    "ours": Path(r"C:\Users\MACAU\Desktop\pack28.zip"),
    "donor": ROOT / "extracted" / "public_asset_baseline" / "artifacts" / "intermediate" / "donor_submission.zip",
    "base": ROOT / "extracted" / "public_asset_baseline" / "artifacts" / "intermediate" / "base_submission.zip",
}

want = ("item_002", "item_029", "item_030")


def extract_item(zpath: Path, tag: str) -> None:
    dest = OUT / tag
    dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if any(f"/{item}/" in name or name.endswith(f"/{item}") for item in want):
                out = dest / Path(name).name
                # keep item folder
                parts = Path(name).parts
                item = next(p for p in parts if p.startswith("item_"))
                target_dir = dest / item
                if name.endswith("/"):
                    continue
                rel = Path(*parts[parts.index(item):])
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))


for tag, p in zips.items():
    extract_item(p, tag)


def dump_usd(path: Path) -> None:
    print(f"\n===== {path} size={path.stat().st_size} =====")
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        print("FAILED OPEN")
        return
    print("upAxis", UsdGeom.GetStageUpAxis(stage), "meters", UsdGeom.GetStageMetersPerUnit(stage))
    print("defaultPrim", stage.GetDefaultPrim())
    for prim in stage.Traverse():
        t = prim.GetTypeName()
        extra = ""
        if prim.IsA(UsdGeom.Xformable):
            xf = UsdGeom.Xformable(prim)
            extra += f" xformOpCount={len(xf.GetOrderedXformOps())}"
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            pts = mesh.GetPointsAttr().Get()
            extra += f" points={0 if pts is None else len(pts)}"
            counts = mesh.GetFaceVertexCountsAttr().Get()
            extra += f" faces={0 if counts is None else len(counts)}"
        refs = []
        for spec in prim.GetPrimStack():
            pass
        # materials / refs in metadata
        print(f"  {prim.GetPath()} type={t}{extra}")
        if t in ("Shader", "Material"):
            for attr in prim.GetAttributes():
                val = attr.Get()
                if val is not None and ("texture" in attr.GetName().lower() or "file" in attr.GetName().lower() or "diffuse" in attr.GetName().lower()):
                    print(f"      {attr.GetName()}={val}")


for tag in ("theirs", "ours", "donor", "base"):
    for item in want:
        usd = OUT / tag / item / f"{item}.usd"
        if usd.exists():
            dump_usd(usd)
        else:
            print("MISSING", usd)
