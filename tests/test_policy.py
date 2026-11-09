from dataclasses import replace

from podglass.adv import Advert
from podglass.config import Config
from podglass.policy import (
    Action, AdvertSeen, Bluez, CaVolumeChanged, Command, ConnectFailed, EarChanged, InputActivity,
    Policy, Tick, emit,
)

BASE = Advert(addr="70:81:94:0D:FB:AA", rssi=-50, model="pro2-usbc", paired=True, primary_left=True,
              left=80, right=80, case=60, left_charging=False, right_charging=False, case_charging=False,
              left_in_ear=False, right_in_ear=False, lid_open=True, lid_known=True, lid_counter=1, conn_state=0)



def seen(known=True, **kw):
    return AdvertSeen(replace(BASE, **kw), known=known)


LID_OPEN = seen(lid_open=True)
LID_CLOSED = seen(lid_open=False)
IN_EAR = seen(lid_known=False, left_in_ear=True, right_in_ear=True)
SETUP = AdvertSeen(Advert(addr="11:22:33:44:55:66", rssi=-40, model="pro2-usbc", paired=False), known=False)


def names(actions):
    return [a.name if a.name != "emit" else f"emit:{a.arg}" for a in actions]


def policy(**cfg):
    return Policy(Config(**cfg))


# --- table rows (PLAN.md 3.2) -----------------------------------------------------------------

def test_lid_open_shows_card():
    assert names(policy().step(LID_OPEN, 0)) == ["emit:lid-opened", "show_card"]


def test_lid_closed_hides_card_after_delay():
    p = policy()
    p.step(LID_OPEN, 0)
    assert names(p.step(LID_CLOSED, 10)) == ["emit:lid-closed"]
    assert p.next_deadline() == 11.5
    assert p.step(Tick(), 11.4) == []
    assert p.step(Tick(), 11.5) == [Action("hide_card")]
    assert p.next_deadline() is None


def test_lid_open_autoconnect():
    p = policy(autoconnect="lid-open")
    assert names(p.step(LID_OPEN, 0)) == ["emit:lid-opened", "show_card", "connect"]


def test_lid_open_no_autoconnect_when_busy_elsewhere():
    p = Policy(Config(autoconnect="lid-open"), busy_states=frozenset({0x0B}))
    assert "connect" not in names(p.step(seen(lid_open=True, conn_state=0x0B), 0))


def test_lid_open_no_autoconnect_in_ear_mode():
    assert "connect" not in names(policy(autoconnect="in-ear").step(LID_OPEN, 0))


def test_in_ear_connects_when_user_is_here():
    p = policy()
    p.step(InputActivity(), 0)
    assert names(p.step(IN_EAR, 100)) == ["connect"]


def test_in_ear_no_connect_without_recent_input():
    p = policy()
    assert p.step(IN_EAR, 0) == []
    p.step(InputActivity(), 0)
    assert p.step(IN_EAR, 601) == []


def test_in_ear_no_connect_when_never_or_busy():
    p = policy(autoconnect="never")
    p.step(InputActivity(), 0)
    assert p.step(IN_EAR, 1) == []
    p = Policy(Config(), busy_states=frozenset({0x0B}))
    p.step(InputActivity(), 0)
    assert p.step(seen(lid_known=False, left_in_ear=True, conn_state=0x0B), 1) == []


def test_unknown_airpods_never_autoconnect():
    p = policy(autoconnect="lid-open")
    p.step(InputActivity(), 0)
    assert names(p.step(seen(known=False, lid_open=True, left_in_ear=True), 1)) == ["emit:lid-opened", "show_card"]


def test_setup_card_for_close_pairing_mode_airpods():
    p = policy()
    assert p.step(SETUP, 0) == [Action("show_card", "setup"), emit("setup-available")]


def test_setup_card_needs_rssi_and_not_recently_shown():
    p = policy()
    assert p.step(replace(SETUP, adv=replace(SETUP.adv, rssi=-55)), 0) == []
    p.step(SETUP, 0)
    p.step(Command("dismiss-card"), 1)
    assert p.step(SETUP, 299) == []
    assert names(p.step(SETUP, 300)) == ["show_card", "emit:setup-available"]


def test_pod_removed_pauses_and_reinsert_resumes():
    p = policy()
    p.step(EarChanged(True, True), 0)
    assert names(p.step(EarChanged(False, True), 10)) == ["emit:ear-out", "pause_media"]
    assert names(p.step(EarChanged(True, True), 70)) == ["emit:ear-in", "resume_media"]


def test_reinsert_after_window_does_not_resume():
    p = policy()
    p.step(EarChanged(True, True), 0)
    p.step(EarChanged(True, False), 10)
    assert names(p.step(EarChanged(True, True), 71)) == ["emit:ear-in"]


def test_ear_pause_off():
    p = policy(ear_pause=False)
    p.step(EarChanged(True, True), 0)
    assert names(p.step(EarChanged(False, True), 1)) == ["emit:ear-out"]


def test_second_pod_out_does_not_pause_twice():
    p = policy()
    p.step(EarChanged(True, True), 0)
    p.step(EarChanged(False, True), 1)
    assert names(p.step(EarChanged(False, False), 2)) == ["emit:ear-out"]


def test_conversation_awareness_ducks_and_restores():
    p = policy(ca_duck_volume=0.25)
    assert p.step(CaVolumeChanged(1), 0) == [Action("duck_volume", 0.25)]
    assert p.step(CaVolumeChanged(2), 1) == []
    assert p.step(CaVolumeChanged(3), 2) == [Action("restore_volume")]
    assert p.step(CaVolumeChanged(8), 3) == []
    p.step(CaVolumeChanged(2), 4)
    assert p.step(CaVolumeChanged(9), 5) == [Action("restore_volume")]


def test_conversation_awareness_setting_off():
    assert policy(ca_duck=False).step(CaVolumeChanged(1), 0) == []


def test_connect_fails():
    p = policy()
    p.step(Command("connect"), 0)
    assert p.step(ConnectFailed(), 5) == [emit("connect-failed")]
    assert not p.connecting


def test_bluez_connected_and_disconnected():
    p = policy()
    assert names(p.step(Bluez(True), 0)) == ["start_aap", "show_tray", "emit:connected"]
    assert p.step(Bluez(True), 1) == []
    assert names(p.step(Bluez(False), 2)) == ["stop_aap", "hide_tray", "emit:disconnected"]
    assert p.step(Bluez(False), 3) == []


# --- extra rules ------------------------------------------------------------------------------

def test_no_connect_while_connecting():
    p = policy()
    p.step(InputActivity(), 0)
    assert names(p.step(IN_EAR, 1)) == ["connect"]
    assert p.step(IN_EAR, 2) == []
    assert p.step(Command("connect"), 3) == []


def test_no_connect_while_connected():
    p = policy()
    p.step(InputActivity(), 0)
    p.step(Bluez(True), 0)
    assert p.step(IN_EAR, 1) == []


def test_no_second_show_card_while_lid_stays_open():
    p = policy()
    p.step(LID_OPEN, 0)
    assert p.step(LID_OPEN, 1) == []
    assert p.step(seen(lid_open=True, lid_known=False), 2) == []
    assert p.step(LID_OPEN, 3) == []


def test_hide_cancelled_when_lid_reopens_within_delay():
    p = policy()
    p.step(LID_OPEN, 0)
    p.step(LID_CLOSED, 10)
    assert names(p.step(LID_OPEN, 11)) == ["emit:lid-opened"]
    assert p.next_deadline() is None
    assert p.step(Tick(), 12) == []
    assert p.card == "normal"


def test_card_shows_again_after_it_left():
    p = policy()
    p.step(LID_OPEN, 0)
    p.step(LID_CLOSED, 1)
    p.step(Tick(), 3)
    assert names(p.step(LID_OPEN, 4)) == ["emit:lid-opened", "show_card"]


def test_dismiss_card():
    p = policy()
    p.step(LID_OPEN, 0)
    assert p.step(Command("dismiss-card"), 1) == [Action("hide_card")]
    assert p.step(LID_OPEN, 2) == []
    assert p.step(Command("dismiss-card"), 3) == []


def test_card_timeout():
    p = policy(card_timeout_s=8)
    p.step(LID_OPEN, 0)
    assert p.next_deadline() == 8
    assert p.step(Tick(), 8) == [Action("hide_card")]


def test_retry_cooldown_after_failure():
    p = policy()
    p.step(InputActivity(), 0)
    p.step(IN_EAR, 1)
    p.step(ConnectFailed(), 2)
    assert p.step(IN_EAR, 31) == []
    assert names(p.step(IN_EAR, 32)) == ["connect"]


def test_user_disconnect_blocks_autoconnect_until_pods_leave_ears():
    p = policy()
    p.step(InputActivity(), 0)
    p.step(Bluez(True), 0)
    assert p.step(Command("disconnect"), 1) == [Action("disconnect")]
    p.step(Bluez(False), 2)
    assert p.step(IN_EAR, 3) == []
    p.step(seen(lid_known=False), 4)  # pods out of the ears
    assert names(p.step(IN_EAR, 5)) == ["connect"]


def test_user_disconnect_cleared_by_lid_close():
    p = policy()
    p.step(InputActivity(), 0)
    p.step(Command("disconnect"), 1)
    p.step(LID_CLOSED, 2)
    assert names(p.step(IN_EAR, 3)) == ["connect"]


def test_disconnect_restores_ducked_volume():
    p = policy()
    p.step(Bluez(True), 0)
    p.step(CaVolumeChanged(1), 1)
    assert names(p.step(Bluez(False), 2))[-1] == "restore_volume"


def test_first_lid_closed_sighting_emits_nothing():
    assert policy().step(LID_CLOSED, 0) == []
