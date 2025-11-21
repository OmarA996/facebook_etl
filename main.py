import sys

from src.etl.pipelines.meta_insights_daily import run_meta_insights_daily
from src.etl.pipelines.meta_insights_range import run_meta_insights_range


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python main.py insights-daily [level]")
        print("  python main.py insights-range <from_date> <to_date> [level] [chunk_days]")
        return

    command = args[0]

    # ================= DAILY PIPELINE =================
    if command == "insights-daily":
        level = args[1] if len(args) >= 2 else "ad"

        print(f"[main] Running daily insights pipeline (level={level})...")
        run_meta_insights_daily(
            level=level,
            to_db=True,
        )

    # ================= RANGE PIPELINE =================
    elif command == "insights-range":
        if len(args) < 3:
            print("Usage: python main.py insights-range YYYY-MM-DD YYYY-MM-DD [level] [chunk_days]")
            return

        from_date = args[1]
        to_date = args[2]
        level = args[3] if len(args) >= 4 else "ad"
        chunk_days = int(args[4]) if len(args) >= 5 else 7

        print(f"[main] Running range insights pipeline...")
        print(f"       From: {from_date}")
        print(f"       To:   {to_date}")
        print(f"       Level: {level}")
        print(f"       Chunk size: {chunk_days} days")

        run_meta_insights_range(
            level=level,
            from_date=from_date,
            to_date=to_date,
            chunk_size_days=chunk_days,
            to_db=True,
        )

    # ================= UNKNOWN COMMAND =================
    else:
        print(f"[main] Unknown command: {command}")
        print("Available commands:")
        print("  insights-daily")
        print("  insights-range")


if __name__ == "__main__":
    main()
