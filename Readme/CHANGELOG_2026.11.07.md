# Conversational Assistant 2026.11.7.1 — Home Assistant Marketplace readiness

## Changes

- Added Marketplace-compatible repository metadata, documentation, issue tracker, and integration categories; retained the legacy HACS minimum version where existing APIs permit.
- Moved Assist sentence trigger registration from the config entry setup path to a config-entry-owned, cancellable background task starting after Home Assistant reaches running state. Cooperative registration yields between grammar groups; learned triggers load after static groups and storage restoration.
- Preserved async Store restoration and added bounded retry (30 s, 120 s, 480 s) after I/O failures. The integration refuses to overwrite prior Store data before it has been successfully restored.
- Added privacy-safe diagnostics for storage/Assist readiness, operational counters, and registration timing.
- Added startup, restoration, and Assist-registration logs; removed raw stored reminder/command records and webhook response dumps from diagnostic logs.
- Removed release workflow that force-updated a published Git tag. Added immutable tag/version verification and HACS/hassfest/Python regression validation CI.
- Fixed Vietnamese numbered STT selections such as “chọn số lăm” and numeric device names such as “Camera 1” / “Camera 10”.
- Added eight isolated regression tests, including storage restore failure/success handling, deferred Assist registration, and release metadata/workflow checks.
- Updated marketplace installation guidance and instructions for troubleshooting.

## Caveats

- Running the full integration, HACS Action, and hassfest against Home Assistant Core requires a Home Assistant test environment/GitHub Actions; these are not simulated by syntax checks.
- Assist commands become available shortly after Home Assistant starts; existing Zalo webhook service and sensors still initialize during config-entry setup.
- For releases, commit manifest version, then create the matching new GitHub Release tag (e.g. `v2026.11.7.1`). Never retarget a published release tag.
