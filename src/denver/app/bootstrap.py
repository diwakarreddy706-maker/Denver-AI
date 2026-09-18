"""Denver Application Bootstrap and CLI Entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from typing import Sequence

from denver import __version__, assistant_name, product_name
from denver.app.application import DenverApplication
from denver.config.settings import DenverSettings, get_settings


def build_parser() -> argparse.ArgumentParser:
    """Build Denver CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="denver",
        description=f"{product_name} - Windows-First Local & Cloud Intelligent Desktop Assistant",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Display version and product identity.",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Generate a system health report and exit.",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Run self-healing diagnostics and apply safe automated repairs.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate and print sanitized configuration then exit.",
    )
    parser.add_argument(
        "--export-diagnostics",
        nargs="?",
        const="data/diagnostics.json",
        type=str,
        help="Export a sanitized zero-secret diagnostic bundle to JSON.",
    )
    parser.add_argument(
        "--export-memory",
        nargs="?",
        const="data/memory_export.json",
        type=str,
        help="Export a sanitized zero-secret memory snapshot to JSON.",
    )
    parser.add_argument(
        "--verify-release",
        type=str,
        help="Audit a distribution folder or ZIP archive for zero-secret safety and package integrity.",
    )
    parser.add_argument(
        "--build-portable",
        nargs="?",
        const="dist",
        type=str,
        help="Build a verified zero-secret Windows portable distribution package.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions without modifying or creating files.",
    )
    parser.add_argument(
        "-c", "--command",
        type=str,
        help="Execute a single text command through Denver and exit.",
    )
    parser.add_argument(
        "--gui", "--cockpit",
        action="store_true",
        help="Launch the Denver Cockpit desktop graphical interface.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Denver in headless voice-assistant mode without GUI.",
    )
    parser.add_argument(
        "--import-contacts",
        type=str,
        help="Import contacts from a Google Contacts / Outlook CSV file.",
    )
    parser.add_argument(
        "--scan-apps",
        action="store_true",
        help="Scan installed Windows applications, shortcuts, folders, and websites.",
    )
    return parser


async def _run_app(app: DenverApplication) -> None:
    """Run application with signal handling."""
    loop = asyncio.get_running_loop()

    def _handle_signal():
        print(f"\n[{assistant_name}] Shutdown signal received. Cleaning up...")
        asyncio.create_task(app.stop(reason="user_interrupt"))

    # Register OS signals if supported on current platform
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, AttributeError):
            # Windows signal handler fallback is handled in try/except KeyboardInterrupt
            pass

    print(
        f"""
╔════════════════════════════════════════════════════╗
║             {product_name.upper()}             ║
║                  Version {__version__}                     ║
╚════════════════════════════════════════════════════╝
Status: STANDBY
(Press Ctrl+C to shut down)
"""
    )

    try:
        await app.run_forever()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(f"\n[{assistant_name}] Shutting down...")
        await app.stop(reason="keyboard_interrupt")


def main(argv: Sequence[str] | None = None) -> int:
    """Primary entry point for Denver AI Assistant."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"{product_name} v{__version__} ({assistant_name})")
        return 0

    settings = get_settings()

    if args.check_config:
        safe_config = settings.to_safe_dict()
        print(json.dumps(safe_config, indent=2))
        return 0

    if args.repair:
        from denver.health.repair import SystemRepairManager
        manager = SystemRepairManager(settings=settings)
        report = manager.run_repair(dry_run=False)
        print(f"[{assistant_name}] System Health & Auto-Repair Report:")
        print(f"  • Issues Detected: {report.issues_detected}")
        print(f"  • Issues Repaired: {report.issues_fixed}")
        if report.directories_created:
            print(f"  • Directories Created: {', '.join(report.directories_created)}")
        if report.database_optimized:
            print("  • Database: VACUUM & ANALYZE optimization completed")
        if report.logs_rotated:
            print(f"  • Logs Rotated: {', '.join(report.logs_rotated)}")
        if report.temp_files_cleared:
            print(f"  • Temporary Files Cleared: {report.temp_files_cleared} ({report.bytes_freed} bytes freed)")
        print(f"[{assistant_name}] Status: {report.format_spoken_summary()}")
        return 0

    if args.export_diagnostics:
        from denver.health.health_service import DenverHealthService
        hs = DenverHealthService()
        out_path = args.export_diagnostics or "data/diagnostics.json"
        bundle = hs.export_safe_diagnostics(target_path=out_path)
        print(f"[{assistant_name}] Safe diagnostic bundle successfully written to: {out_path}")
        print(json.dumps({k: v for k, v in bundle.items() if k != "configuration"}, indent=2))
        return 0

    if args.export_memory:
        from denver.memory.database import DenverDatabase
        from denver.memory.memory_service import MemoryService
        db = DenverDatabase()
        mem = MemoryService(db=db)
        out_path = args.export_memory or "data/memory_export.json"

        async def _do_export():
            await db.initialize()
            try:
                res = await mem.export_safe_memory(export_path=out_path)
                print(f"[{assistant_name}] Safe memory snapshot successfully written to: {out_path}")
                print(json.dumps({"schema_version": res["schema_version"], "counts": res["counts"]}, indent=2))
            finally:
                await db.close()

        asyncio.run(_do_export())
        return 0

    if args.verify_release:
        from denver.release.verifier import ReleaseArtifactVerifier
        verifier = ReleaseArtifactVerifier()
        report = verifier.verify_target(args.verify_release)
        print(f"[{assistant_name}] " + report.format_summary().replace("\n", f"\n[{assistant_name}] "))
        return 0 if report.is_valid else 1

    if args.build_portable is not None:
        from denver.release.builder import PortableReleaseBuilder
        builder = PortableReleaseBuilder()
        out_dir = args.build_portable or "dist"
        is_dry = bool(args.dry_run)
        print(f"[{assistant_name}] Staging portable release build (dry_run={is_dry})...")
        res = builder.build(output_dir=out_dir, dry_run=is_dry)
        print(res.format_summary())
        return 0 if res.success else 1

    if args.import_contacts:
        from denver.memory.contacts import get_contact_book
        cb = get_contact_book()
        try:
            count = cb.import_from_csv(args.import_contacts)
            print(f"[{assistant_name}] Successfully imported {count} contacts into data/contacts.json")
            return 0
        except Exception as exc:
            print(f"[{assistant_name}] Failed to import contacts: {exc}")
            return 1

    if args.scan_apps:
        from denver.automation.apps_scanner import WindowsAppScanner
        scanner = WindowsAppScanner()
        try:
            apps = scanner.scan_all()
            print(f"[{assistant_name}] Successfully discovered and saved {len(apps)} apps & shortcuts to data/apps.json")
            return 0
        except Exception as exc:
            print(f"[{assistant_name}] Failed to scan apps: {exc}")
            return 1

    app = DenverApplication(settings=settings)

    if args.health:
        health_report = app.health_service.get_health_report()
        print(json.dumps(health_report, indent=2))
        return 0

    if args.command:
        async def _exec_single():
            await app.start()
            try:
                res = await app.process_command(args.command)
                print(json.dumps(res.to_dict(), indent=2))
            finally:
                await app.stop()

        asyncio.run(_exec_single())
        return 0

    if args.gui:
        try:
            from denver.ui.app import DenverCockpitApp
            cockpit = DenverCockpitApp(denver_app=app)
            return cockpit.run()
        except Exception as exc:
            print(f"[{assistant_name}] Failed to start Cockpit GUI: {exc}")
            return 1

    try:
        asyncio.run(_run_app(app))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
