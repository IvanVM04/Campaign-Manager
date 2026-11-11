"""Render a report-only package coverage summary from Cobertura XML."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple


class CoverageStats(NamedTuple):
    package: str
    lines_covered: int
    lines_valid: int
    branches_covered: int
    branches_valid: int

    @property
    def line_percent(self) -> float:
        return _percentage(self.lines_covered, self.lines_valid)

    @property
    def branch_percent(self) -> float | None:
        if self.branches_valid == 0:
            return None
        return _percentage(self.branches_covered, self.branches_valid)


def _percentage(covered: int, valid: int) -> float:
    return 100.0 * covered / valid if valid else 100.0


def summarize_coverage(report: Path) -> list[CoverageStats]:
    """Aggregate Cobertura class lines by their first path component."""
    root = ET.parse(report).getroot()
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])

    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        parts = Path(filename).parts
        package = parts[0] if len(parts) > 1 else "(root)"
        values = totals[package]

        for line in class_node.findall("./lines/line"):
            values[1] += 1
            if int(line.attrib.get("hits", "0")) > 0:
                values[0] += 1

            if line.attrib.get("branch") == "true":
                match = re.search(r"\((\d+)/(\d+)\)", line.attrib.get("condition-coverage", ""))
                if match:
                    values[2] += int(match.group(1))
                    values[3] += int(match.group(2))

    return [
        CoverageStats(package, *totals[package])
        for package in sorted(totals)
    ]


def render_markdown(stats: list[CoverageStats]) -> str:
    lines = [
        "## Python coverage by top-level package",
        "",
        "| Package | Lines | Line coverage | Branches | Branch coverage |",
        "|---|---:|---:|---:|---:|",
    ]

    for item in stats:
        branch_count = f"{item.branches_covered}/{item.branches_valid}"
        branch_percent = (
            f"{item.branch_percent:.1f}%"
            if item.branch_percent is not None
            else "n/a"
        )
        lines.append(
            f"| {item.package} | {item.lines_covered}/{item.lines_valid} "
            f"| {item.line_percent:.1f}% | {branch_count} | {branch_percent} |"
        )

    total_lines_covered = sum(item.lines_covered for item in stats)
    total_lines_valid = sum(item.lines_valid for item in stats)
    total_branches_covered = sum(item.branches_covered for item in stats)
    total_branches_valid = sum(item.branches_valid for item in stats)
    total_line_percent = _percentage(total_lines_covered, total_lines_valid)
    total_branch_percent = (
        f"{_percentage(total_branches_covered, total_branches_valid):.1f}%"
        if total_branches_valid
        else "n/a"
    )
    lines.extend(
        [
            f"| **Total** | **{total_lines_covered}/{total_lines_valid}** "
            f"| **{total_line_percent:.1f}%** "
            f"| **{total_branches_covered}/{total_branches_valid}** "
            f"| **{total_branch_percent}** |",
            "",
            "_Report only: these figures do not impose a coverage threshold._",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to coverage.xml")
    parser.add_argument(
        "--github-summary",
        type=Path,
        help="Append the Markdown report to this GitHub Actions summary file.",
    )
    args = parser.parse_args()

    if not args.report.exists():
        message = f"Coverage report unavailable: {args.report}"
        print(message)
        if args.github_summary:
            with args.github_summary.open("a", encoding="utf-8") as output:
                output.write(f"## Python coverage by package\n\n{message}\n")
        return 0

    markdown = render_markdown(summarize_coverage(args.report))
    print(markdown, end="")
    if args.github_summary:
        with args.github_summary.open("a", encoding="utf-8") as output:
            output.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
