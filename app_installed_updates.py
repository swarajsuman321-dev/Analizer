"""Compatibility entry point for complete, acknowledged Setup updates."""
from app_update_launcher import launch_transaction


def launch_setup_update(download, recovery, directory, manifest):
    if manifest.get('kind') != 'installer':
        raise ValueError('Installed updates require the Setup package')
    return launch_transaction(download, recovery, directory, manifest)
