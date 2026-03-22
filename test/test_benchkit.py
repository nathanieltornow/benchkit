"""Tests for the function-first BenchKit workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
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


def test_decorated_sweep_binds_analysis_tables_and_figures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("build-perf")
    def build_perf(size: int) -> None:
        bk.context().save_json("summary.json", {"compile_time_ms": float(size), "throughput": 0.9})
        bk.context().save_result({"compile_time_ms": float(size), "throughput": 0.9})

    analysis = build_perf.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)
    frame = analysis.load_frame()
    table_path = analysis.save_dataframe(frame, "results")

    with bk.pplot():
        fig, ax = plt.subplots()
        summary_df = frame.groupby("config.size", as_index=False)[["result.compile_time_ms"]].mean()
        ax.plot(summary_df["config.size"], summary_df["result.compile_time_ms"], marker="o")

    figure_paths = analysis.save_figure(fig, plot_name="build-perf")
    plt.close(fig)

    assert table_path == analysis._data_dir / "results.parquet"
    assert table_path.exists()
    assert len(figure_paths) == 2
    assert all(path.exists() for path in figure_paths)


def test_single_call_uses_current_sweep_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("single-case")
    def single_case(size: int) -> None:
        bk.context().save_result({"compile_time_ms": float(size)})

    first = single_case(size=8)
    second = single_case(size=16)

    assert first.sweep_id == second.sweep_id
    analysis = bk.open_analysis("single-case")
    assert analysis.get_run(config={"size": 8}, status=bk.RunStatus.OK).metrics == {"compile_time_ms": 8.0}
    assert analysis.get_run(config={"size": 16}, status=bk.RunStatus.OK).metrics == {"compile_time_ms": 16.0}


def test_save_result_overwrites_and_append_result_keeps_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("sample-logging")
    def sampled(size: int) -> None:
        bk.context().append_result({"sample_ms": size + 1})
        bk.context().append_result({"sample_ms": size + 2})
        bk.context().save_result({"compile_time_ms": float(size)})
        bk.context().save_result({"compile_time_ms": float(size + 10)})

    run = sampled(size=8)

    assert run.metrics == {"compile_time_ms": 18.0}
    assert run.load_json("metrics.json") == {"compile_time_ms": 18.0}
    assert run.path("results.jsonl").read_text(encoding="utf-8").splitlines() == [
        '{"sample_ms": 9}',
        '{"sample_ms": 10}',
    ]


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


def test_open_analysis_supports_reopening_without_function_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    analysis = nested_layout.sweep(cases=[{"size": 8}], sweep="sweep-a", show_progress=False)
    run = analysis.get_run(config={"size": 8}, status=bk.RunStatus.OK)

    relative = run.artifact_dir.relative_to(tmp_path / "home")
    assert relative.parts[:3] == ("runs", "nested-layout", "sweep-a")


def test_completed_cases_are_skipped_in_same_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))
    calls = {"count": 0}

    @bk.func("resume-benchmark")
    def resume_benchmark(size: int) -> None:
        calls["count"] += 1
        bk.context().save_json("raw.json", {"size": size})
        bk.context().save_result({"compile_time_ms": float(size)})

    resume_benchmark.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)
    resume_benchmark.sweep(cases=[{"size": 8}, {"size": 16}], show_progress=False)

    assert calls["count"] == 2


def test_open_analysis_defaults_to_latest_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))

    @bk.func("default-sweep-benchmark")
    def default_sweep_benchmark(size: int) -> None:
        bk.context().save_result({"compile_time_ms": float(size)})

    default_sweep_benchmark.sweep(cases=[{"size": 8}], sweep="sweep-a", show_progress=False)
    default_sweep_benchmark.sweep(cases=[{"size": 16}], sweep="sweep-b", show_progress=False, new_sweep=True)

    analysis = bk.open_analysis("default-sweep-benchmark")
    assert analysis.sweep == "sweep-b"
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


def test_parallel_sweep_produces_same_results_as_sequential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_parallel_sweep_resumes_correctly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))
    calls = {"count": 0}

    @bk.func("parallel-resume")
    def parallel_resume(size: int) -> None:
        calls["count"] += 1
        bk.context().save_result({"value": float(size)})

    # Same cases twice -- second call resumes and skips completed
    cases = [{"size": 1}, {"size": 2}, {"size": 3}]
    parallel_resume.sweep(cases=cases, show_progress=False, max_workers=2)
    parallel_resume.sweep(cases=cases, show_progress=False, max_workers=2)

    assert calls["count"] == 3


def test_different_cases_get_different_sweeps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHKIT_HOME", str(tmp_path / "home"))
    calls = {"count": 0}

    @bk.func("different-cases")
    def different_cases(size: int) -> None:
        calls["count"] += 1
        bk.context().save_result({"value": float(size)})

    a1 = different_cases.sweep(cases=[{"size": 1}, {"size": 2}], show_progress=False)
    a2 = different_cases.sweep(cases=[{"size": 1}, {"size": 2}, {"size": 3}], show_progress=False)

    # Different case lists = different sweeps = all cases run
    assert a1.sweep_id != a2.sweep_id
    assert calls["count"] == 5
