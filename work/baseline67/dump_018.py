from pxr import Usd, UsdGeom, UsdPhysics, Gf
from pathlib import Path

path = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\inspect\pack28\item_018\item_018.usd")
stage = Usd.Stage.Open(str(path))
for prim in stage.Traverse():
    print("=" * 60)
    print(prim.GetPath(), prim.GetTypeName(), list(prim.GetAppliedSchemas()))
    if prim.IsA(UsdGeom.Xformable):
        xf = UsdGeom.Xformable(prim)
        for op in xf.GetOrderedXformOps():
            print("  op", op.GetOpName(), op.GetOpType(), op.Get())
    if prim.IsA(UsdGeom.Mesh):
        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            zs = [p[2] for p in pts]
            print("  mesh local", (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs)), "n", len(pts))
    if prim.IsA(UsdPhysics.Joint):
        j = UsdPhysics.Joint(prim)
        for name in (
            "physics:body0",
            "physics:body1",
            "physics:localPos0",
            "physics:localPos1",
            "physics:localRot0",
            "physics:localRot1",
            "physics:axis",
            "physics:lowerLimit",
            "physics:upperLimit",
        ):
            attr = prim.GetAttribute(name)
            if attr:
                print(" ", name, attr.Get())
        print("  rels", [(r.GetName(), r.GetTargets()) for r in prim.GetRelationships()])
