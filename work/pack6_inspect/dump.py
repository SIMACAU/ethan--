import zipfile
from pathlib import Path

from pxr import Usd, UsdGeom, UsdPhysics

zip_path = Path("output/submission_pack6_20260824.zip")
extract = Path("work/pack6_inspect")
extract.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path) as archive:
    archive.extractall(extract)

root = extract / "submission"
print("PACK6_CONTENTS")
for item in sorted(root.glob("item_*")):
    usd = item / f"{item.name}.usd"
    stage = Usd.Stage.Open(str(usd))
    meshes = [p.GetName() for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    xforms = [p.GetName() for p in stage.Traverse() if p.GetTypeName() == "Xform"]
    joints = [(p.GetName(), p.GetTypeName()) for p in stage.Traverse() if "Joint" in p.GetTypeName()]
    rigid = sum(1 for p in stage.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], True)
    default = stage.GetDefaultPrim()
    dims = [0, 0, 0]
    if default:
        size = cache.ComputeWorldBound(default).ComputeAlignedRange().GetSize()
        dims = [round(float(size[i]), 3) for i in range(3)]
    print(
        f"{item.name} meshes={len(meshes)} rigid={rigid} joints={[j[0] for j in joints]} "
        f"size={dims} parts={xforms[:12]}"
    )
