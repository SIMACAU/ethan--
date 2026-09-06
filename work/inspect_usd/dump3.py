from pxr import Usd, UsdPhysics
stage = Usd.Stage.Open(r"C:\Users\MACAU\Desktop\天池\work\inspect_usd\item_013_front.usd")
for prim in stage.Traverse():
    t=prim.GetTypeName()
    if t in ("Xform","PhysicsPrismaticJoint","PhysicsRevoluteJoint") and ("lever" in prim.GetName() or "knob" in prim.GetName() or "button" in prim.GetName() or "Joint" in t or prim.GetName()=="Body"):
        extra=""
        if "Joint" in t:
            extra=f" pos0={prim.GetAttribute('physics:localPos0').Get()} pos1={prim.GetAttribute('physics:localPos1').Get()} axis={prim.GetAttribute('physics:axis').Get()}"
        print(prim.GetPath(), t, extra)
