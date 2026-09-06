from pxr import Usd, UsdGeom
from pathlib import Path

path = Path(r"C:\Users\MACAU\Desktop\天池\work\baseline67\inspect\pack28\item_022\item_022.usd")
stage = Usd.Stage.Open(str(path))
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], True)
for prim in stage.Traverse():
    if not prim.IsA(UsdGeom.Xformable):
        continue
    rng = cache.ComputeWorldBound(prim).GetRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    print(
        f"{prim.GetPath()} {prim.GetTypeName()} "
        f"size=({mx[0]-mn[0]:.4f},{mx[1]-mn[1]:.4f},{mx[2]-mn[2]:.4f}) "
        f"z={mn[2]:.4f}:{mx[2]:.4f} y={mn[1]:.4f}:{mx[1]:.4f} x={mn[0]:.4f}:{mx[0]:.4f}"
    )
