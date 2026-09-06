from pxr import Usd, UsdGeom, UsdPhysics
from pathlib import Path

for name in ["item_001","item_013","item_018"]:
    path = Path(r"C:\Users\MACAU\Desktop\天池\work\inspect_usd") / f"{name}.usd"
    stage = Usd.Stage.Open(str(path))
    print("="*60)
    print(name, "default", stage.GetDefaultPrim().GetPath())
    print("up", UsdGeom.GetStageUpAxis(stage), "mpu", UsdGeom.GetStageMetersPerUnit(stage))
    root = stage.GetDefaultPrim()
    print("custom", dict(root.GetCustomData()))
    for prim in stage.Traverse():
        apis = list(prim.GetAppliedSchemas())
        extra = ""
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            extra += " RIGID"
            rb = UsdPhysics.RigidBodyAPI(prim)
            extra += f" kin={rb.GetKinematicEnabledAttr().Get()} en={rb.GetRigidBodyEnabledAttr().Get()}"
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            extra += " COLL"
        if prim.HasAPI(UsdPhysics.MassAPI):
            m = UsdPhysics.MassAPI(prim)
            extra += f" mass={m.GetMassAttr().Get()} dens={m.GetDensityAttr().Get()}"
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            extra += " ARTIC"
        t = prim.GetTypeName()
        if "Joint" in t:
            extra += f" JOINT"
            for attr in prim.GetAttributes():
                extra += f" {attr.GetName()}={attr.Get()}"
            for rel in prim.GetRelationships():
                extra += f" {rel.GetName()}->{list(rel.GetTargets())}"
        if apis or extra or t in ("Xform","Mesh"):
            print(f"  {prim.GetPath()} [{t}] {apis}{extra}")
