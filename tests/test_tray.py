from podglass.tray import SIZE, Menu, pods_pixmap, tooltip_text


def test_pixmap_shape_and_content():
    px = pods_pixmap()
    assert len(px) == SIZE * SIZE * 4
    alphas = px[0::4]
    assert alphas[0] == 0  # transparent corner
    assert sum(a == 255 for a in alphas) > 40  # the glyph is there


def test_tooltip():
    assert tooltip_text("AirPods Pro", 82, 80, None) == "AirPods Pro - L 82% R 80% Case -"


def test_menu_layout_and_clicks():
    clicks = []
    m = Menu(lambda v, a: clicks.append((v, a)))
    m.mode = "anc"
    root_id, _, children = m.layout()
    assert root_id == 0 and len(children) == 7
    states = {c.value[0]: c.value[1].get("toggle-state") for c in children}
    assert states[4].value == 1 and states[1].value == 0
    for item in (2, 5, 6, 7):
        m.click(item)
    assert clicks == [("mode", "transparency"), ("disconnect", None), ("edit", None)]
