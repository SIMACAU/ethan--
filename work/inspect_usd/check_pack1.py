from pxr import Usd, UsdGeom, UsdPhysics, UsdShade
import sys

checks = {
    "item_001": ["handle_left", "handle_right", "door_left_joint"],
    "item_014": ["door_handle", "door_window", "shell_back", "door_joint"],
    "item_018": ["keyboard", "touchpad", "screen_joint"],
    "item_012": ["knob_1", "drawer_1_joint"],
    "item_002": [],
}
ok = True
for item, names in checks.items():
    path = rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd"
    stage = Usd.Stage.Open(path)
    all_names = {p.GetName() for p in stage.Traverse()}
    missing = [n for n in names if n not in all_names]
    has_tex = any(p.GetTypeName() == "Shader" and "Image" in p.GetName() for p in stage.Traverse())
    joints = [p.GetName() for p in stage.Traverse() if "Joint" in p.GetTypeName() and p.GetTypeName() != "Xform"]
    print(item, "missing:", missing, "| texture:", has_tex, "| joints:", len(joints))
    if missing or not has_tex:
        ok = False
print("ALL_OK" if ok else "PROBLEM")
