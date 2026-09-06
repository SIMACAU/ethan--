from pxr import Usd, UsdGeom, UsdPhysics
checks = {
    "item_004": ["cushion", "back_left", "leg_0", "caster_4", "swivel_joint"],
    "item_017": ["base", "spout", "handle", "lid_joint"],
    "item_033": ["glass_door", "glass_wall_left", "frame_post_1", "table_top", "glass_door_joint", "cabinet_door_joint", "drawer_joint", "faucet_joint"],
    "item_034": ["door", "door_knob", "window", "blind", "Cabinet", "WhiteCabinet", "door_joint", "cabinet_door_joint", "desk_drawer_joint", "blind_joint"],
}
ok = True
for item, names in checks.items():
    path = rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd"
    stage = Usd.Stage.Open(path)
    all_names = {p.GetName() for p in stage.Traverse()}
    missing = [n for n in names if n not in all_names]
    joints = [p.GetName() for p in stage.Traverse() if "Joint" in str(p.GetTypeName())]
    has_tex = any("Image" in p.GetName() for p in stage.Traverse() if str(p.GetTypeName()) == "Shader")
    print(item, "missing:", missing, "| joints:", joints, "| texture:", has_tex)
    if missing:
        ok = False
print("ALL_OK" if ok else "PROBLEM")
