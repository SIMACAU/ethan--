from pxr import Usd, UsdShade
stage = Usd.Stage.Open(r"C:\Users\MACAU\Desktop\天池\output\submission\submission\item_013\item_013.usd")
for prim in stage.Traverse():
    t=prim.GetTypeName()
    if t in ("Material","Shader"):
        print(prim.GetPath(), t)
        if t=="Shader":
            shader=UsdShade.Shader(prim)
            print("  id", shader.GetIdAttr().Get())
            for inp in shader.GetInputs():
                val=inp.Get()
                if val is not None:
                    print("  ", inp.GetBaseName(), val)
