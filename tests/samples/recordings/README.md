# Reusable real recordings

The user supplied these four recordings on 18 October 2026 and explicitly requested that their original files be published to this GitHub repository for future testing. Original names and bytes are preserved. [manifest.json](manifest.json) records size and SHA-256; `.gitattributes` prevents line-ending conversion. Combined size: 31,452,392 bytes.

| Role | Source rows | Projected numeric channels | End coordinate (min) |
| --- | ---: | ---: | ---: |
| TDMS | 11,363 | 27 | 232.366501 |
| Power PD | 15,898 | 11 | 264.95 |
| Machine RD | 57,494 | 24 | 265.020733 |
| Simulation | 106,148 | 29 | 176.91 |

TDMS channels have different sample counts. The simulation supplied here differs from the recording described in older handovers. The filenames describe different loads and runs: successful import or numerical comparison does not establish physical comparability or appliance acceptance. Unknown units must be confirmed before interpreting physical calculations.

From the repository root, using the installed project environment:

```sh
python tools/verify_recording_samples.py
QT_QPA_PLATFORM=offscreen python tools/audit_user_workflows.py --output /tmp/analizer-user-audit
```

The diagnostic exits 1 when user requirements are unmet. Inspect its JSON summary: application callback errors and audit-runner errors are counted separately. Output/settings use the specified output directory; original recordings are checked again after the audit.

For all 15 nonempty file combinations, use `tools/audit_recordings.py --input PATH` four times with the manifest's original filenames, `--full-workspace --output /tmp/analizer-recordings`. Engineering checks use `tools/audit_engineering_recordings.py` with `--power`, `--machine`, `--tdms`, `--simulation` and `--output` (see each script's `--help`). Set writable cache/settings/output environment directories when running in a restricted cloud account.

[User workflow findings and screenshots](../../../docs/audits/2026-10-18-real-user-workflows/README.md).
