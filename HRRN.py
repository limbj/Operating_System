"""Legacy compatibility wrapper for the HRRN scheduler."""

from scheduler import legacy_run


def main(Info=None):
    if Info is None:
        Info = []
    return legacy_run(Info, "HRRN")


if __name__ == "__main__":
    raise SystemExit("이 모듈은 GUI 또는 다른 Python 코드에서 main(Info)로 호출하세요.")
