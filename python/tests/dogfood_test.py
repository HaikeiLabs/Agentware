"""End-to-end dogfood: enforced ingest → deny/retry → contradiction → inference."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pgmpy", reason="install the 'inference' extra")

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "python" / "examples"
sys.path.insert(0, str(EXAMPLES))

from wiki_memory_dogfood import TBOX_PATHS, run  # noqa: E402


@pytest.fixture(scope="session")
def memctl(tmp_path_factory: pytest.TempPathFactory) -> str:
    if shutil.which("go") is None:
        pytest.skip("go toolchain unavailable")
    if not Path(TBOX_PATHS[0]).exists():
        pytest.skip("ontologies submodule missing (git submodule update --init)")
    binary = tmp_path_factory.mktemp("bin") / "memctl"
    subprocess.run(
        ["go", "build", "-o", str(binary), "./cmd/memctl"],
        cwd=REPO_ROOT / "go",
        check=True,
        capture_output=True,
    )
    return str(binary)


def test_dogfood_scenario(
    memctl: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PEDRO_MEMCTL", memctl)
    report = run(str(tmp_path / "memory"))

    # Deny→retry cycle happened and was driven by the diagnostics.
    assert len(report["deny_log"]) == 1
    assert report["deny_log"][0]["constraint"] == "unknown-concept"
    assert report["deny_log"][0]["corrected_to"] == "twitch:Go"

    # The contradicting 4th source lowers the earlier claim's confidence...
    assert report["final_c1"] < report["baseline_c1"]
    # ...and the contested flag sets on the contradiction (the weakly
    # sourced opposing claim faces a confident counterpart).
    assert report["contested_c3"] is True
    assert report["final_c3"] < 0.5

    # Confidence landed back in the vault through the enforced write path.
    written = report["written_back"]
    assert written["c1"]["confidence"] == pytest.approx(report["final_c1"])
    assert written["c3"]["contested"] is True
