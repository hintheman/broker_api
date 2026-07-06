from datetime import datetime, timezone

start_ms = int(datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
end_ms   = int(datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)

print(start_ms, end_ms)
