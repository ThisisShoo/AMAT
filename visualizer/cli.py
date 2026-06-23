from __future__ import annotations

import argparse
from pathlib import Path

from .report_writer import write_report
from .scene_builder import build_scene
from .three_renderer import render_three_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render AMAT generated mission trajectories as interactive 3D HTML.")
    sub = parser.add_subparsers(dest="command")

    view = sub.add_parser("view", help="Render a generated mission.")
    view.add_argument(
        "mission_id",
        nargs="?",
        help="Mission ID under generated/<mission_id>. Optional when --mission-dir is provided.",
    )
    view.add_argument("--root", default=".", help="AMAT project root. Defaults to current directory.")
    view.add_argument(
        "--mission-dir",
        default=None,
        help="Explicit mission artifact directory containing outputs/, or a parent containing simulation/outputs/.",
    )
    view.add_argument("--html", default=None, help="Optional output HTML path.")
    view.add_argument("--report", default=None, help="Optional output report JSON path.")
    view.add_argument(
        "--renderer",
        choices=("three", "plotly"),
        default="three",
        help="HTML renderer to use. Defaults to the Three.js viewer.",
    )

    args = parser.parse_args(argv)
    if args.command != "view":
        parser.print_help()
        return 2
    if not args.mission_id and not args.mission_dir:
        view.error("provide mission_id or --mission-dir")

    scene, paths = build_scene(Path(args.root), mission_id=args.mission_id, mission_dir=args.mission_dir)
    if args.renderer == "plotly":
        from .plotly_renderer import render_html

        html_path = render_html(scene, paths, args.html)
    else:
        html_path = render_three_html(scene, paths, args.html)
    report_path = write_report(scene, paths, args.report)

    print(f"Mission:  {paths.mission_id}")
    print(f"Source:   {paths.mission_dir}")
    print(f"Renderer: {args.renderer}")
    print(f"Rendered: {html_path}")
    print(f"Report:   {report_path}")
    if scene.warnings:
        print("Warnings:")
        for warning in scene.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
