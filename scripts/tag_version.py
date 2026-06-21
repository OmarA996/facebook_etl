import argparse
import datetime as _dt
import re
import subprocess
import sys


def _run(cmd, check=True):
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=True,
    )


def _ensure_git_repo():
    try:
        _run(["git", "rev-parse", "--git-dir"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit("Not a git repository or git is unavailable.") from exc


def _ensure_tag_not_exists(tag):
    existing = _run(["git", "tag", "-l", tag]).stdout.strip()
    if existing:
        raise SystemExit(f"Tag already exists: {tag}")


def _stage_and_commit(version, date_str, message):
    _run(["git", "add", "-A"])

    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        text=True,
    )
    if diff.returncode == 0:
        return False
    if diff.returncode != 1:
        raise SystemExit("Failed to check staged changes.")

    commit_message = message or f"Snapshot {version} ({date_str})"
    _run(["git", "commit", "-m", commit_message])
    return True


def _valid_date(date_str):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False
    try:
        _dt.date.fromisoformat(date_str)
    except ValueError:
        return False
    return True


def main(argv):
    parser = argparse.ArgumentParser(
        description="Commit changes (if any) and create an annotated version tag."
    )
    parser.add_argument("version", help="Version number, e.g. 1.0.0")
    parser.add_argument(
        "--date",
        help="Date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--message",
        help="Commit message to use when creating a commit.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Skip committing; only create the tag on the current commit.",
    )

    args = parser.parse_args(argv)

    date_str = args.date or _dt.date.today().isoformat()
    if not _valid_date(date_str):
        raise SystemExit("Date must be in YYYY-MM-DD format.")

    _ensure_git_repo()

    tag = f"v{args.version}-{date_str}"
    _ensure_tag_not_exists(tag)

    committed = False
    if not args.no_commit:
        committed = _stage_and_commit(args.version, date_str, args.message)

    _run(["git", "tag", "-a", tag, "-m", f"Version {args.version} ({date_str})"])

    if committed:
        print(f"Committed and tagged: {tag}")
    elif args.no_commit:
        print(f"Tagged without commit: {tag}")
    else:
        print(f"No changes to commit. Tagged existing commit: {tag}")


if __name__ == "__main__":
    main(sys.argv[1:])
