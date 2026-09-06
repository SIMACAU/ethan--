from pxr import Usd
checks = {
    "item_005": ["shade", "pole", "switch", "shade_joint"],
    "item_006": ["arm_left", "back_1", "back_2", "leg_4"],
    "item_007": ["back", "leg_4"],
    "item_008": ["leg_1", "leg_4"],
    "item_009": ["leg_4"],
    "item_014": ["dial", "button_5", "window_frame", "door_joint", "dial_joint"],
    "item_015": ["button", "display", "lid_joint", "button_joint"],
    "item_016": ["handle", "window_l", "knob_time", "knob_temp", "basket_joint", "knob_time_joint"],
    "item_020": ["red_ring", "stand_l", "tilt_joint"],
    "item_023": ["handle_top", "handle_bot"],
    "item_024": ["rim"],
}
ok = True
for item, names in checks.items():
    path = rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd"
    stage = Usd.Stage.Open(path)
    all_names = {p.GetName() for p in stage.Traverse()}
    missing = [n for n in names if n not in all_names]
    extra_lid = "lid_joint" in all_names if item == "item_024" else False
    print(item, "missing:", missing, "bad_lid" if extra_lid else "")
    if missing or extra_lid:
        ok = False
print("ALL_OK" if ok else "PROBLEM")
