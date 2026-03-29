"""Tests for the function-first BenchKit workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

import benchkit as bk
from benchkit.config import benchkit_home

if TYPE_CHECKING:
    from pathlib import Path


def test_benchkit_home_defaults_to_project_local_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "project"
    nested_dir = project_dir / "subdir" / "deeper"
    nested_dir.mkdir(parents=True)
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    monkeypatch.delenv("BENCHKIT_HOME", raising=False)
    monkeypatch.chdir(nested_dir)

    assert benchkit_home() == project_dir / ".benchkit"


def test_sweep_runs_cases_and_produces_analysis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("build-perf")
    def build_perf(size: int) -> None:
        bk.context().save_json("summary.json", {"compile_time_ms": float(size), "throughput": 0.9})
        bk.context().save_result({"compile_time_ms": float(size), "throughput": 0.9})

    analysis = build_perf.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)
    frame = analysis.load_frame()

    assert len(frame) == 2
    assert set(frame.columns) >= {"config.size", "result.compile_time_ms", "result.throughput", "status"}
    assert sorted(frame["config.size"]) == [8, 16]


def test_single_call_returns_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("single-case")
    def single_case(size: int) -> None:
        bk.context().save_result({"compile_time_ms": float(size)})

    run = single_case(size=8)

    assert run.metrics == {"compile_time_ms": 8.0}
    analysis = bk.open_analysis("single-case")
    assert analysis.get_run(config={"size": 8}, status=bk.RunStatus.OK).metrics == {"compile_time_ms": 8.0}


def test_multiple_save_result_creates_repetitions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("repetitions")
    def repeated(size: int) -> None:
        for i in range(3):
            bk.context().save_result({"rep": i, "time_ms": float(size + i)})

    analysis = repeated.sweep(cases=[{"size": 8}], show_progress=False)
    runs = analysis.load_runs(status=bk.RunStatus.OK)

    assert len(runs) == 3
    assert [r.rep for r in runs] == [0, 1, 2]
    assert [r.metrics["time_ms"] for r in runs] == [8.0, 9.0, 10.0]

    frame = analysis.load_frame()
    assert len(frame) == 3
    assert list(frame["rep"]) == [0, 1, 2]


def test_run_helper_captures_command_outputs_as_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("run-helper")
    def run_helper(size: int) -> None:
        result = bk.run(
            ["python3", "-c", "import sys; print('hello'); print('warn', file=sys.stderr)"],
            name="compiler",
        )
        bk.context().save_result({"compile_time_ms": float(size), "returncode": float(result.returncode)})

    run = run_helper(size=8)

    assert run.read_text("compiler.stdout.txt") == "hello\n"
    assert run.read_text("compiler.stderr.txt") == "warn\n"
    metadata = run.load_json("compiler.run.json")
    assert metadata["args"][0] == "python3"
    assert metadata["returncode"] == 0


def test_open_analysis_reopens_stored_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("reopen-study")
    def reopen_study(size: int) -> None:
        bk.context().save_json("trace.json", {"size": size})
        bk.context().save_result({"compile_time_ms": float(size)})

    reopen_study(size=8)

    analysis = bk.open_analysis("reopen-study")
    frame = analysis.load_frame()
    run = analysis.get_run(config={"size": 8}, status=bk.RunStatus.OK)

    assert frame.loc[0, "result.compile_time_ms"] == pytest.approx(8.0)
    assert run.load_json("trace.json") == {"size": 8}


def test_top_level_load_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("top-level-load")
    def top_level_load(n: int) -> None:
        bk.context().save_result({"value": float(n)})

    top_level_load.sweep(cases=[{"n": 1}, {"n": 2}], show_progress=False)

    frame = bk.load_frame("top-level-load")
    assert len(frame) == 2
    assert list(frame["result.value"]) == [1.0, 2.0]

    runs = bk.load_runs("top-level-load", status=bk.RunStatus.OK)
    assert len(runs) == 2


def test_analysis_is_iterable_over_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("iter-analysis")
    def iter_analysis(size: int) -> None:
        bk.context().save_result({"compile_time_ms": float(size)})

    iter_analysis.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)
    analysis = bk.open_analysis("iter-analysis")

    sizes = sorted(run.config["size"] for run in analysis if run.status is bk.RunStatus.OK)
    assert sizes == [8, 16]


def test_explicit_case_objects_are_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @dataclass(frozen=True)
    class Case:
        size: int
        backend: str

    @bk.func("case-object-benchmark")
    def case_object_benchmark(size: int, backend: str) -> None:
        bk.context().save_json("raw.json", {"size": size, "backend": backend})
        bk.context().save_result({"compile_time_ms": float(size)})

    analysis = case_object_benchmark.sweep(
        cases=[Case(size=8, backend="cpu"), Case(size=16, backend="gpu")],
        show_progress=False,
    )

    assert analysis.get_run(config={"size": 8, "backend": "cpu"}, status=bk.RunStatus.OK).metrics == {
        "compile_time_ms": 8.0
    }
    assert analysis.get_run(config={"size": 16, "backend": "gpu"}, status=bk.RunStatus.OK).metrics == {
        "compile_time_ms": 16.0
    }


def test_run_folders_are_nested_by_benchmark_and_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("nested-layout")
    def nested_layout(size: int) -> None:
        bk.context().save_json("raw.json", {"size": size})
        bk.context().save_result({"compile_time_ms": float(size)})

    analysis = nested_layout.sweep(cases=[{"size": 8}], show_progress=False)
    run = analysis.get_run(config={"size": 8}, status=bk.RunStatus.OK)

    assert run.artifact_dir is not None
    relative = run.artifact_dir.relative_to(tmp_path / "home")
    assert relative.parts[0] == "runs"
    assert relative.parts[1] == "nested-layout"
    assert len(relative.parts) >= 4  # runs/benchmark/sweep/case_key


def test_resume_skips_completed_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))
    calls = {"count": 0}

    @bk.func("resume-benchmark")
    def resume_benchmark(size: int) -> None:
        calls["count"] += 1
        bk.context().save_result({"compile_time_ms": float(size)})

    # First call runs 2 cases
    resume_benchmark.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)

    # Second call with resume=True -- completed cases skipped, new case runs
    resume_benchmark.sweep(
        cases=[{"size": 8}, {"size": 16}, {"size": 32}],
        show_progress=False,
        resume=True,
    )

    assert calls["count"] == 3


def test_open_analysis_defaults_to_latest_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("default-sweep-benchmark")
    def default_sweep_benchmark(size: int) -> None:
        bk.context().save_result({"compile_time_ms": float(size)})

    # First sweep
    a1 = default_sweep_benchmark.sweep(cases=[{"size": 8}], show_progress=False)

    # Second sweep (fresh by default)
    a2 = default_sweep_benchmark.sweep(cases=[{"size": 16}], show_progress=False)

    assert a1.sweep_id != a2.sweep_id
    analysis = bk.open_analysis("default-sweep-benchmark")
    assert analysis.sweep == a2.sweep_id
    assert analysis.get_run(config={"size": 16}, status=bk.RunStatus.OK).metrics == {"compile_time_ms": 16.0}


def test_failed_runs_expose_error_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("failing-benchmark")
    def failing_benchmark(size: int) -> None:
        if size == 8:
            msg = "boom"
            raise RuntimeError(msg)
        bk.context().save_result({"compile_time_ms": float(size)})

    analysis = failing_benchmark.sweep(cases=[{"size": 8}], show_progress=False)
    run = analysis.get_run(config={"size": 8}, status=bk.RunStatus.FAILURE)

    assert run.error_type == "RuntimeError"
    assert run.error_message == "boom"


def test_parallel_sweep_produces_correct_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("parallel-benchmark")
    def parallel_benchmark(size: int) -> None:
        bk.context().save_json("raw.json", {"size": size})
        bk.context().save_result({"compile_time_ms": float(size)})

    analysis = parallel_benchmark.sweep(
        cases=[{"size": s} for s in range(1, 9)],
        show_progress=False,
        max_workers=4,
    )

    runs = analysis.load_runs(status=bk.RunStatus.OK)
    assert len(runs) == 8
    sizes = sorted(run.config["size"] for run in runs)
    assert sizes == list(range(1, 9))
    for run in runs:
        assert run.metrics == {"compile_time_ms": float(run.config["size"])}


def test_default_sweep_starts_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))
    calls = {"count": 0}

    @bk.func("fresh-sweep")
    def fresh_sweep(size: int) -> None:
        calls["count"] += 1
        bk.context().save_result({"value": float(size)})

    a1 = fresh_sweep.sweep(cases=[{"size": 1}], show_progress=False)

    # By default, second call starts a fresh sweep (re-runs cases)
    a2 = fresh_sweep.sweep(cases=[{"size": 1}], show_progress=False)
    assert a2.sweep_id != a1.sweep_id
    assert calls["count"] == 2

    # With resume=True, resumes the latest sweep (skips completed)
    a3 = fresh_sweep.sweep(cases=[{"size": 1}], show_progress=False, resume=True)
    assert a3.sweep_id == a2.sweep_id
    assert calls["count"] == 2

    # BENCHKIT_RESUME=1 env var also triggers resume
    monkeypatch.setenv("BENCHKIT_RESUME", "1")
    a4 = fresh_sweep.sweep(cases=[{"size": 1}], show_progress=False)
    assert a4.sweep_id == a2.sweep_id
    assert calls["count"] == 2
