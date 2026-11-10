import asyncio

from podglass.media import Media


class Fake:
    def __init__(self, replies):
        self.replies = replies  # tuple(args) -> (code, out)
        self.calls = []

    async def __call__(self, args):
        self.calls.append(args)
        return self.replies.get(tuple(args), (0, ""))


def test_pause_only_playing_players_and_resume_them():
    fake = Fake({("playerctl", "-l"): (0, "spotify\nfirefox.instance1\n"),
                 ("playerctl", "-p", "spotify", "status"): (0, "Playing\n"),
                 ("playerctl", "-p", "firefox.instance1", "status"): (0, "Paused\n")})
    m = Media(fake)
    asyncio.run(m.pause())
    asyncio.run(m.pause())  # second removal: nothing new
    assert ["playerctl", "-p", "spotify", "pause"] in fake.calls
    assert ["playerctl", "-p", "firefox.instance1", "pause"] not in fake.calls
    asyncio.run(m.resume())
    assert fake.calls[-1] == ["playerctl", "-p", "spotify", "play"]
    asyncio.run(m.resume())  # nothing left to resume
    assert fake.calls[-1] == ["playerctl", "-p", "spotify", "play"]


def test_no_players():
    fake = Fake({("playerctl", "-l"): (1, "")})
    asyncio.run(Media(fake).pause())
    assert fake.calls == [["playerctl", "-l"]]


def test_duck_and_restore():
    fake = Fake({("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"): (0, "Volume: 0.80\n")})
    m = Media(fake)
    asyncio.run(m.duck(0.3))
    asyncio.run(m.duck(0.3))
    asyncio.run(m.restore())
    sets = [c for c in fake.calls if c[1] == "set-volume"]
    assert sets == [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.30"],
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.80"]]


def test_no_duck_when_already_quiet():
    fake = Fake({("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"): (0, "Volume: 0.20\n")})
    m = Media(fake)
    asyncio.run(m.duck(0.3))
    asyncio.run(m.restore())
    assert not [c for c in fake.calls if c[1] == "set-volume"]
