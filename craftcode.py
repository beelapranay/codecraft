from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import typer
from git import Repo
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - optional dependency
    genai = None
    genai_types = None

cli = typer.Typer(add_completion=False)
console = Console()

DEFAULT_CONTEXT_LIMIT = 60_000
MAX_FILE_CONTEXT_CHARS = 8_000
ENV_FILE = Path(__file__).resolve().parent / ".env"

SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}

SKIP_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}

REPORT_TEMPLATE = {
    "summary": {
        "overall_grade": "B",
        "health_score": 72,
        "total_issues": 0,
        "critical_issues": 0,
    },
    "missing_tests": [],
    "styling_issues": [],
    "design_pattern_issues": [],
    "clean_code_violations": [],
    "ci_cd_issues": [],
    "security_issues": [],
    "dependency_issues": [],
    "top_priorities": [],
}

SCORING_WEIGHTS = {
    "missing_tests": 1,
    "styling_issues": 1,
    "design_pattern_issues": 0,
    "ci_cd_issues": 2,
    "dependency_issues": 2,
}

SCORING_CAPS = {
    "missing_tests": 6,
    "styling_issues": 4,
    "design_pattern_issues": 0,
    "ci_cd_issues": 6,
    "dependency_issues": 6,
    "clean_code_violations": 10,
    "security_issues": 24,
}

SEVERITY_WEIGHTS = {
    "security_issues": {"high": 10, "medium": 5, "low": 2},
    "clean_code_violations": {"high": 3, "medium": 2, "low": 1},
}


@dataclass(frozen=True)
class ScanResult:
    root: Path
    files: list[Path]
    content: str


def load_local_env(env_path: Path = ENV_FILE) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


def is_github_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and parsed.netloc in {"github.com", "www.github.com"}


def normalize_repo_path(path: str) -> Path:
    expanded = Path(path).expanduser()
    if not expanded.exists():
        raise FileNotFoundError("Target path does not exist.")

    resolved = expanded.resolve()
    if resolved.is_file():
        return resolved.parent
    if not resolved.is_dir():
        raise NotADirectoryError("Target must be a directory or a file inside a directory.")
    return resolved


def collect_source_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Repository root not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository root must be a directory: {root}")

    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def read_file_safely(path: Path, max_chars: int = MAX_FILE_CONTEXT_CHARS) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as file_handle:
        content = file_handle.read(max_chars + 1)

    if len(content) > max_chars:
        return content[:max_chars].rstrip() + "\n# ... truncated"
    return content


def build_context(files: list[Path], root: Path, char_limit: int = DEFAULT_CONTEXT_LIMIT) -> str:
    chunks: list[str] = []
    total = 0

    for path in files:
        relative = path.relative_to(root)
        content = read_file_safely(path)
        prefix = f"### FILE: {relative.as_posix()}\n```\n"
        suffix = "\n```\n"
        available = char_limit - total - len(prefix) - len(suffix)

        if available <= 0:
            break

        if len(content) > available:
            content = content[: max(0, available - len("\n# ... truncated"))].rstrip() + "\n# ... truncated"

        block = f"{prefix}{content}{suffix}"
        chunks.append(block)
        total += len(block)

        if total >= char_limit:
            break

    return "\n".join(chunks)


def scan_repository(root: Path, char_limit: int = DEFAULT_CONTEXT_LIMIT) -> ScanResult:
    files = collect_source_files(root)
    content = build_context(files, root, char_limit=char_limit)
    return ScanResult(root=root, files=files, content=content)


def clone_github_repo(repo_url: str) -> tuple[Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="craftcode-"))
    target_dir = temp_dir / "repo"
    Repo.clone_from(repo_url, target_dir)
    return temp_dir, target_dir


def strip_json_fences(text: str) -> str:
    stripped = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    if "```" in stripped:
        cleaned = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()
    return stripped


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_json_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain valid JSON.")
    return json.loads(cleaned[start : end + 1])


def summarize_local_scan(scan: ScanResult) -> dict[str, Any]:
    styling_file = next((path for path in scan.files if path.suffix.lower() in {".css", ".scss", ".less", ".html", ".tsx", ".jsx"}), None)
    sample_file = scan.files[0] if scan.files else None

    return {
        "summary": {
            "overall_grade": "B",
            "health_score": 72,
            "total_issues": 0,
            "critical_issues": 0,
        },
        "missing_tests": [
            {
                "file": str(sample_file.relative_to(scan.root)) if sample_file else "",
                "reason": "Fallback mode cannot inspect test depth, so coverage gaps should be reviewed manually.",
                "suggested_test": "Add integration tests for the main user flow and regression tests around failure cases.",
            }
        ] if sample_file else [],
        "styling_issues": [
            {
                "file": str(styling_file.relative_to(scan.root)) if styling_file else "",
                "issue": "Styling review is unavailable in fallback mode, so visual consistency has not been validated.",
                "impact": "Layout, spacing, and accessibility problems may go unreported without LLM analysis.",
                "fix": "Set GEMINI_API_KEY to enable a full design and maintainability review.",
            }
        ] if styling_file else [],
        "design_pattern_issues": [
            {
                "file": str(sample_file.relative_to(scan.root)) if sample_file else "",
                "issue": "Pattern recommendations are limited when the analyzer is running without a model.",
                "pattern_applicable": "Factory, strategy, adapter, and dependency-injection opportunities are not inferred offline.",
                "fix": "Enable the model-backed path to surface architectural refactors grounded in the scanned code.",
            }
        ] if sample_file else [],
        "clean_code_violations": [],
        "ci_cd_issues": [
            {
                "issue": "No CI workflow is generated or checked by the scaffold.",
                "fix": "Add automated lint, test, and build checks before relying on report output in a team workflow.",
            }
        ],
        "security_issues": [],
        "dependency_issues": [
            {
                "issue": "The live code review path depends on Gemini credentials and falls back to a scaffold without them.",
                "fix": "Install google-genai and set GEMINI_API_KEY before running a real repository review.",
            }
        ],
        "top_priorities": [
            "Enable the model-backed review so the report can inspect styling, tests, and architectural gaps in the actual code.",
            "Add automated tests that cover scanning, prompt construction, JSON parsing, and web request handling.",
            "Add CI before expanding the app so regressions in the analyzer and UI are caught early.",
        ],
    }


def build_system_prompt() -> str:
    return (
        "You are a principal engineer reviewing a full software repository.\n"
        "Analyze the codebase for styling and frontend consistency issues, missing or weak tests, "
        "clean code violations, architecture and design-pattern opportunities, CI/CD gaps, "
        "security issues, dependency risks, and practical improvements.\n"
        "When appropriate, recommend patterns such as factory, strategy, adapter, dependency injection, "
        "builder, or observer, but only when they fit the code.\n"
        "The application computes the final score deterministically, so prioritize accurate findings over inventing a score.\n"
        "Reference concrete files and logic whenever possible.\n"
        "Return ONLY valid JSON with no markdown or preamble."
    )


def build_user_prompt(scan: ScanResult) -> str:
    return (
        "Return this exact JSON shape:\n"
        "{\n"
        '  "summary": {\n'
        '    "overall_grade": "A/B/C/D/F",\n'
        '    "health_score": 0-100,\n'
        '    "total_issues": number,\n'
        '    "critical_issues": number\n'
        "  },\n"
        '  "missing_tests": [\n'
        '    { "file": "", "reason": "", "suggested_test": "" }\n'
        "  ],\n"
        '  "styling_issues": [\n'
        '    { "file": "", "issue": "", "impact": "", "fix": "" }\n'
        "  ],\n"
        '  "design_pattern_issues": [\n'
        '    { "file": "", "issue": "", "pattern_applicable": "", "fix": "" }\n'
        "  ],\n"
        '  "clean_code_violations": [\n'
        '    { "file": "", "violation": "", "severity": "high/medium/low", "fix": "" }\n'
        "  ],\n"
        '  "ci_cd_issues": [\n'
        '    { "issue": "", "fix": "" }\n'
        "  ],\n"
        '  "security_issues": [\n'
        '    { "file": "", "issue": "", "severity": "high/medium/low", "fix": "" }\n'
        "  ],\n"
        '  "dependency_issues": [\n'
        '    { "issue": "", "fix": "" }\n'
        "  ],\n"
        '  "top_priorities": ["...", "...", "..."]\n'
        "}\n\n"
        "Review emphasis:\n"
        "- styling, layout, and frontend maintainability problems\n"
        "- tests that are missing, brittle, or too shallow\n"
        "- clean code and readability issues\n"
        "- architectural improvements and useful design patterns\n"
        "- CI/CD, security, and dependency concerns\n\n"
        "Important:\n"
        "- The backend recalculates summary score and grade deterministically.\n"
        "- Focus on accurate issue lists; summary values may be placeholders.\n\n"
        f"Repository root: {scan.root}\n"
        f"Files scanned: {len(scan.files)}\n\n"
        f"Codebase:\n{scan.content}"
    )


def score_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def issue_count(report: dict[str, Any], key: str) -> int:
    value = report.get(key, [])
    return len(value) if isinstance(value, list) else 0


def severity_penalty(rows: list[dict[str, Any]], key: str) -> int:
    weights = SEVERITY_WEIGHTS[key]
    total = 0
    for row in rows:
        severity = str(row.get("severity", "")).lower()
        total += weights.get(severity, weights["low"])
    return min(total, SCORING_CAPS[key])


def fixed_penalty(report: dict[str, Any], key: str) -> int:
    count = issue_count(report, key)
    return min(count * SCORING_WEIGHTS[key], SCORING_CAPS[key])


def compute_summary(report: dict[str, Any]) -> dict[str, Any]:
    baseline = 95
    penalties = 0
    penalties += fixed_penalty(report, "missing_tests")
    penalties += fixed_penalty(report, "styling_issues")
    penalties += fixed_penalty(report, "design_pattern_issues")
    penalties += fixed_penalty(report, "ci_cd_issues")
    penalties += fixed_penalty(report, "dependency_issues")
    penalties += severity_penalty(report.get("clean_code_violations", []), "clean_code_violations")
    penalties += severity_penalty(report.get("security_issues", []), "security_issues")

    bonuses = 0
    if issue_count(report, "security_issues") == 0:
        bonuses += 5
    if issue_count(report, "dependency_issues") == 0:
        bonuses += 3
    if issue_count(report, "ci_cd_issues") == 0:
        bonuses += 2

    score = max(0, min(100, baseline - penalties + bonuses))
    critical_issues = sum(
        1
        for issue in report.get("security_issues", [])
        if str(issue.get("severity", "")).lower() == "high"
    )
    total_issues = (
        issue_count(report, "missing_tests")
        + issue_count(report, "styling_issues")
        + issue_count(report, "design_pattern_issues")
        + issue_count(report, "clean_code_violations")
        + issue_count(report, "ci_cd_issues")
        + issue_count(report, "security_issues")
        + issue_count(report, "dependency_issues")
    )

    if critical_issues == 0:
        score = max(score, 70)
    if issue_count(report, "security_issues") == 0 and issue_count(report, "clean_code_violations") <= 3:
        score = max(score, 78)

    return {
        "overall_grade": score_grade(score),
        "health_score": score,
        "total_issues": total_issues,
        "critical_issues": critical_issues,
    }


def merge_report(report: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(REPORT_TEMPLATE))
    for key, value in report.items():
        if key not in merged:
            continue

        default_value = merged[key]
        if isinstance(default_value, dict) and isinstance(value, dict):
            default_value.update(value)
            merged[key] = default_value
            continue

        if isinstance(default_value, list) and isinstance(value, list):
            merged[key] = value
            continue

        merged[key] = value
    merged["summary"] = compute_summary(merged)
    return merged


def analyze_with_llm(scan: ScanResult) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if genai is None or genai_types is None or not api_key:
        return summarize_local_scan(scan)

    client = genai.Client(api_key=api_key)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(description="Running LLM analysis...", total=None)
        response = client.models.generate_content(
            model=os.getenv("CRAFTCODE_MODEL", "gemini-2.5-flash"),
            contents=build_user_prompt(scan),
            config=genai_types.GenerateContentConfig(
                system_instruction=build_system_prompt(),
                response_mime_type="application/json",
                temperature=0.2,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )

    content = response.text or ""
    report = extract_json_object(content)
    return merge_report(report)


def analyze_target(target: str, char_limit: int = DEFAULT_CONTEXT_LIMIT) -> dict[str, Any]:
    temp_dir: Optional[Path] = None
    try:
        if is_github_url(target):
            temp_dir, repo_root = clone_github_repo(target)
        else:
            repo_root = normalize_repo_path(target)

        scan = scan_repository(repo_root, char_limit=char_limit)
        return analyze_with_llm(scan)
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


def severity_style(severity: str) -> str:
    normalized = severity.lower()
    if normalized == "high":
        return "red"
    if normalized == "medium":
        return "yellow"
    if normalized == "low":
        return "green"
    return "white"


def grade_style(grade: str) -> str:
    mapping = {
        "A": "green",
        "B": "cyan",
        "C": "yellow",
        "D": "orange1",
        "F": "red",
    }
    return mapping.get(grade.upper(), "white")


def render_summary(summary: dict[str, Any]) -> None:
    grade = str(summary.get("overall_grade", "?"))
    score = summary.get("health_score", 0)
    total_issues = summary.get("total_issues", 0)
    critical_issues = summary.get("critical_issues", 0)

    panel = Panel(
        Text.assemble(
            (f"Grade: {grade}", grade_style(grade)),
            "   ",
            (f"Score: {score}", "bold"),
            "   ",
            (f"Issues: {total_issues}", "bold"),
            "   ",
            (f"Critical: {critical_issues}", "bold red"),
        ),
        title="Craftcode Summary",
        border_style=grade_style(grade),
    )
    console.print(panel)


def render_table(title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    table = Table(title=title, show_lines=True)
    for column in columns:
        table.add_column(column, style="white", overflow="fold")

    if not rows:
        table.add_row(*(["No findings"] + ["" for _ in range(len(columns) - 1)]))
        console.print(table)
        return

    for row in rows:
        values = []
        for column in columns:
            key = column.lower()
            value = row.get(key, row.get(key.replace(" ", "_"), ""))
            if key == "severity":
                values.append(Text(str(value), style=severity_style(str(value))))
            else:
                values.append(str(value))
        table.add_row(*values)
    console.print(table)


def render_report(report: dict[str, Any]) -> None:
    render_summary(report.get("summary", {}))
    render_table(
        "Missing Tests",
        report.get("missing_tests", []),
        ["file", "reason", "suggested_test"],
    )
    render_table(
        "Styling Issues",
        report.get("styling_issues", []),
        ["file", "issue", "impact", "fix"],
    )
    render_table(
        "Design Pattern Issues",
        report.get("design_pattern_issues", []),
        ["file", "issue", "pattern_applicable", "fix"],
    )
    render_table(
        "Clean Code Violations",
        report.get("clean_code_violations", []),
        ["file", "violation", "severity", "fix"],
    )
    render_table(
        "CI/CD Issues",
        report.get("ci_cd_issues", []),
        ["issue", "fix"],
    )
    render_table(
        "Security Issues",
        report.get("security_issues", []),
        ["file", "issue", "severity", "fix"],
    )
    render_table(
        "Dependency Issues",
        report.get("dependency_issues", []),
        ["issue", "fix"],
    )

    priorities = report.get("top_priorities", [])
    if priorities:
        console.print(Panel("\n".join(str(item) for item in priorities), title="Top Priorities", border_style="cyan"))


def save_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


@cli.command()
def main(
    target: str = typer.Argument(..., help="Local path or GitHub repository URL."),
    json_output: bool = typer.Option(False, "--json", help="Write raw JSON report to craftcode_report.json."),
) -> None:
    try:
        report = analyze_target(target)
        render_report(report)

        if json_output:
            save_report(report, Path.cwd() / "craftcode_report.json")
            console.print("Saved JSON report to craftcode_report.json")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    cli()
