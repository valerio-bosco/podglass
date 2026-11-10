from dbus_fast import Variant

from podglass.bluez import pick_airpods


def dev(addr, name, modalias="bluetooth:v004Cp2014d0500", paired=True, connected=False):
    return {"org.bluez.Device1": {
        "Address": Variant("s", addr), "Name": Variant("s", name), "Modalias": Variant("s", modalias),
        "Paired": Variant("b", paired), "Connected": Variant("b", connected)}}


def test_picks_paired_apple_airpods():
    objs = {
        "/org/bluez/hci0": {"org.bluez.Adapter1": {}},
        "/org/bluez/hci0/dev_A": dev("AA:00:00:00:00:01", "WH-1000XM4", modalias="bluetooth:v0054p0d58"),
        "/org/bluez/hci0/dev_B": dev("2C:32:6A:BC:8F:5D", "AirPods Pro - Find My", connected=True),
    }
    d = pick_airpods(objs)
    assert (d.path, d.address, d.connected) == ("/org/bluez/hci0/dev_B", "2C:32:6A:BC:8F:5D", True)


def test_known_address_wins_and_unpaired_loses():
    objs = {
        "/a": dev("11:11:11:11:11:11", "AirPods Pro", paired=False),
        "/b": dev("22:22:22:22:22:22", "AirPods Pro"),
        "/c": dev("33:33:33:33:33:33", "My headphones"),
    }
    assert pick_airpods(objs).path == "/b"
    assert pick_airpods(objs, {"33:33:33:33:33:33"}).path == "/c"


def test_nothing_found():
    assert pick_airpods({"/x": dev("AA:00:00:00:00:01", "Speaker", modalias="")}) is None
