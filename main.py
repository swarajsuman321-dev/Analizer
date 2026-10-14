"""Standalone Qt application entry point."""
def run():
    from app_workbench import run_workbench
    return run_workbench()


if __name__ == '__main__':
    raise SystemExit(run())
