"""Modern desktop entry point, with lazy access to the original Tk API."""
def __getattr__(name):
    import app_legacy
    return getattr(app_legacy, name)


def run(legacy=False):
    if legacy:
        from app_legacy import ApplianceSignalStudioPro
        ApplianceSignalStudioPro().mainloop()
        return 0
    from app_workbench import run_workbench
    return run_workbench()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy', action='store_true')
    raise SystemExit(run(parser.parse_args().legacy))
