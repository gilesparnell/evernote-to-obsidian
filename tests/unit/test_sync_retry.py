from scripts.sync_retry import parse_wait_seconds


class TestParseWaitSeconds:
    def test_parses_standard_rate_limit_message(self):
        line = "2026-04-23 13:34:53,914 | CRITICAL | Rate limit reached. Restart program in 28:35."
        assert parse_wait_seconds(line) == 28 * 60 + 35

    def test_parses_minutes_only(self):
        assert parse_wait_seconds("Rate limit reached. Restart program in 5:00.") == 300

    def test_parses_seconds_only(self):
        assert parse_wait_seconds("Rate limit reached. Restart program in 0:45.") == 45

    def test_returns_none_when_no_rate_limit(self):
        assert parse_wait_seconds("Synchronization completed!") is None

    def test_returns_none_for_empty_string(self):
        assert parse_wait_seconds("") is None

    def test_returns_none_for_unrelated_log_line(self):
        assert parse_wait_seconds("INFO | Downloading note abc-123") is None

    def test_parses_large_minute_value(self):
        assert parse_wait_seconds("Restart program in 60:00.") == 3600
