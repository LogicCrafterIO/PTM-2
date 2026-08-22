from ptm.log import elapsed_since, eta, log


def test_log_writes_timestamped_line(capsys):
    log("hello progress")
    err = capsys.readouterr().err
    assert "hello progress" in err
    assert err.startswith("[")


def test_eta_and_elapsed():
    started = 0.0
    assert elapsed_since(started)
    assert eta(0, 10, started) == "?"
    assert eta(5, 10, started)
