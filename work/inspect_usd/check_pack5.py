from pxr import Usd
checks = {
    "item_018": ["screen", "logo", "screen_joint"],
    "item_021": ["hang_tab"],
    "item_022": ["roll_12"],
    "item_025": ["seal"],
    "item_033": ["brace", "bin", "ceiling_light", "glass_door_joint"],
    "item_034": ["sofa", "sign", "card_reader", "door_joint"],
}
ok = True
for item, names in checks.items():
    stage = Usd.Stage.Open(rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd")
    all_names = {p.GetName() for p in stage.Traverse()}
    missing = [n for n in names if n not in all_names]
    print(item, "missing:", missing)
    if missing:
        ok = False
print("ALL_OK" if ok else "PROBLEM")
