"""studio.py's pure parts: request parsing, sanitising, bitrate, checks, queue rules.
Nothing here touches the network, the GPU or ffmpeg.

    python test_studio.py        (or python -m pytest test_studio.py -q)
"""
import studio as s


def test_trigger_needs_prefix():
    assert s.is_request("studio: rain on the market")
    assert s.is_request("  Studio: rain")
    assert not s.is_request("can the studio make me something?")
    assert not s.is_request("")
    assert not s.is_request(None)


def test_parse_seconds_and_minutes():
    assert s.parse_request("studio: slow tide, 90s") == ("slow tide", 90)
    assert s.parse_request("studio: slow tide 2 min") == ("slow tide", 120)
    assert s.parse_request("studio: slow tide") == ("slow tide", s.DEFAULT_S)


def test_duration_is_clamped():
    assert s.parse_request("studio: x 5s")[1] == s.MIN_S
    assert s.parse_request("studio: x 999 seconds")[1] == s.MAX_S
    assert s.parse_request("studio: x 9 min")[1] == s.MAX_S


def test_prompt_is_sanitised_and_capped():
    p, _ = s.parse_request("studio: <script>alert(1)</script> [b]neon[/b] {rain} & `rm -rf`")
    assert not set(p) & set("<>[]{}&`/()")
    long, _ = s.parse_request("studio: " + "word " * 200)
    assert len(long) <= s.PROMPT_CHARS


def test_caption_always_carries_trigger_and_instrumental():
    assert s.caption_for("rainy market").startswith("kannakasound, instrumental, ")
    assert s.caption_for("").startswith("kannakasound, instrumental")


def test_title_is_short_and_studio_prefixed():
    t = s.title_for("rainy market at night with distant trains and a slow bell")
    assert t.startswith("Resonance House: Rainy market")
    assert len(t) <= 80
    assert s.title_for("") == "Resonance House: Untitled"
    assert s.title_for("rain on the market awnings at night, slow") == \
        "Resonance House: Rain on the market awnings at night"


def test_bitrate_fits_under_upload_cap():
    for secs in (30, 120, 150, 180):
        kbps = s.bitrate_for(secs)
        assert secs * kbps * 1000 / 8 <= s.UPLOAD_CAP
    assert s.bitrate_for(150) == 320  # the dusk track: 6.0 MB at 320k
    assert s.bitrate_for(180) == 320


def test_check_catches_short_silent_clipped():
    job = {"seconds": 120}
    assert s.check(job, {"seconds": 120.0, "peak_db": -1.0, "rms_db": -16.0}) == []
    assert s.check(job, {"seconds": 60.0, "peak_db": -1.0, "rms_db": -16.0})
    assert s.check(job, {"seconds": 120.0, "peak_db": -1.0, "rms_db": -60.0})
    assert s.check(job, {"seconds": 120.0, "peak_db": 0.0, "rms_db": -16.0})
    assert s.check(job, {"seconds": 120.0, "peak_db": None, "rms_db": None})


def test_jobs_start_pending_and_number_up():
    q = {"jobs": [], "seen": []}
    a = s.new_job(q, "one", 60, "manual")
    b = s.new_job(q, "two", 60, "manual")
    assert (a["id"], b["id"]) == ("job-001", "job-002")
    assert a["state"] == "pending"


def test_move_records_history_and_rejects_unknown_state():
    q = {"jobs": [], "seen": []}
    j = s.new_job(q, "x", 60, "manual")
    s.move(j, "approved", "ok")
    assert j["state"] == "approved" and j["history"][-1]["from"] == "pending"
    try:
        s.move(j, "shipped")
        raise AssertionError("unknown state accepted")
    except AssertionError as e:
        assert "shipped" in str(e)


def test_delivery_needs_explicit_success():
    assert s.delivered_ok({"success": True, "data": {}})
    assert not s.delivered_ok({"success": True, "error": "x"})
    assert not s.delivered_ok({"error": "rate-limited after retries"})
    assert not s.delivered_ok({"success": False})
    assert not s.delivered_ok(None)


def test_daily_cap_counts_only_todays_publishes():
    q = {"jobs": [], "seen": []}
    j = s.new_job(q, "x", 60, "manual")
    j["history"] = [{"at": s.now(), "to": "published"}, {"at": "2020-01-01T00:00:00Z", "to": "published"}]
    assert s.uploads_today(q) == 1


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); n += 1
    print(f"{n} passed")
