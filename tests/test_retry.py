from utils.retry import retry_call


def test_retry_call_recovers_after_failure() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary")
        return "ok"

    assert retry_call(flaky, attempts=3, delay_seconds=0) == "ok"
