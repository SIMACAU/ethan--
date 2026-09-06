from pxr import Usd, UsdGeom, UsdPhysics
from pathlib import Path

for name in ["item_013_new","item_001_new"]:
    path = Path(r"C:\Users\MACAU\Desktop\天池\work\inspect_usd") / f"{name}.usd"
    stage = Usd.Stage.Open(str(path))
    print("="*60, name)
    print("kg", getattr(UsdPhysics, "GetStageKilogramsPerUnit", lambda s: "n/a")(stage))
    for prim in stage.Traverse():
        t = prim.GetTypeName()
        extra = ""
        if prim.HasAPI(UsdPhysics.MassAPI):
            m = UsdPhysics.MassAPI(prim)
            extra += f" mass={m.GetMassAttr().Get()} dens={m.GetDensityAttr().Get()} I={m.GetDiagonalInertiaAttr().Get()} com={m.GetCenterOfMassAttr().Get()}"
        if "Joint" in t:
            extra += f" pos0={prim.GetAttribute('physics:localPos0').Get()} pos1={prim.GetAttribute('physics:localPos1').Get()} lo={prim.GetAttribute('physics:lowerLimit').Get()} hi={prim.GetAttribute('physics:upperLimit').Get()} axis={prim.GetAttribute('physics:axis').Get()}"
        if extra or t in ("Xform","Mesh","PhysicsRevoluteJoint","PhysicsPrismaticJoint"):
            if extra or t != "Mesh":
                print(f"  {prim.GetPath()} [{t}]{extra}")
