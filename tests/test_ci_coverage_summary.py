from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "ci"))

from coverage_summary import render_markdown, summarize_coverage


def test_summarize_coverage_groups_files_by_top_level_package(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        """<?xml version="1.0" ?>
        <coverage>
          <packages>
            <package name=".">
              <classes>
                <class filename="app.py">
                  <lines>
                    <line number="1" hits="1" />
                    <line number="2" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
            <package name="api">
              <classes>
                <class filename="api/handler.py">
                  <lines>
                    <line number="1" hits="1" branch="true"
                          condition-coverage="50% (1/2)" />
                    <line number="2" hits="1" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
        encoding="utf-8",
    )

    stats = summarize_coverage(report)

    assert [(item.package, item.lines_covered, item.lines_valid) for item in stats] == [
        ("(root)", 1, 2),
        ("api", 2, 2),
    ]
    api = stats[1]
    assert api.branches_covered == 1
    assert api.branches_valid == 2
    assert api.branch_percent == 50.0


def test_render_markdown_marks_report_as_informational(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        """<coverage><packages><package name="models"><classes>
        <class filename="models/state.py"><lines>
        <line number="1" hits="1" />
        </lines></class></classes></package></packages></coverage>""",
        encoding="utf-8",
    )

    markdown = render_markdown(summarize_coverage(report))

    assert "| models | 1/1 | 100.0% | 0/0 | n/a |" in markdown
    assert "do not impose a coverage threshold" in markdown
