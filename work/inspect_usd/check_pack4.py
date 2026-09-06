from pxr import Usd
checks = {
    "item_001": ["shelf_3", "handle_left", "door_left_joint", "door_right_joint"],
    "item_002": ["bottle_10", "flap_front_joint"],
    "item_003": ["top", "drawer_2", "door_left_joint", "drawer_2_joint"],
    "item_011": ["shelf", "door", "knob", "door_joint"],
    "item_012": ["knob_6", "drawer_6_joint"],
    "item_019": ["usbc", "dpi", "wheel_joint"],
    "item_030": ["ear_left", "ear_right"],
    "item_032": ["lid", "helper", "lid_joint"],
}
ok = True
for item, names in checks.items():
    path = rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd"
    stage = Usd.Stage.Open(path)
    all_names = {p.GetName() for p in stage.Traverse()}
    missing = [n for n in names if n not in all_names]
    print(item, "missing:", missing)
    if missing:
        ok = False
print("ALL_OK" if ok else "PROBLEM")
