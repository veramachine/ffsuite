"""The workspace's three projects held together: what one decides, the others repeat."""

import ast
import tomllib
from pathlib import Path
from typing import Final, cast

import pytest
from packaging.requirements import Requirement  # the dev group's; in the Nix checks, pytest's

ROOT: Final = Path(__file__).resolve().parents[3]  # packages/ffman/tests/ -> the workspace
PACKAGES: Final = ("ffman", "ffmeta", "subverter")
LIBRARIES: Final = ("ffmeta", "subverter")
LICENSES: Final = ("LICENSE-MIT", "LICENSE-APACHE")
SHARED: Final = ("authors", "maintainers", "requires-python")


def _pyproject(folder: Path) -> dict[str, object]:
    with (folder / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def _project(pyproject: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", pyproject["project"])


def _python_classifiers(project: dict[str, object]) -> list[str]:
    classifiers = cast("list[str]", project["classifiers"])
    return [c for c in classifiers if c.startswith("Programming Language :: Python")]


def test_the_root_is_the_workspaces_alone() -> None:
    # no project of its own (uv's virtual root): its members, every package under packages/
    root = _pyproject(ROOT)
    assert "project" not in root
    tool = cast("dict[str, dict[str, object]]", root["tool"])
    assert tool["uv"]["workspace"] == {"members": ["packages/*"]}
    found = sorted(p.parent.name for p in (ROOT / "packages").glob("*/pyproject.toml"))
    assert found == sorted(PACKAGES)


@pytest.mark.parametrize("package", PACKAGES)
def test_a_packages_licences_are_the_roots(package: str) -> None:
    # a copy each: license-files is the package's own folder's (6.7.5, measured)
    for name in LICENSES:
        assert (ROOT / "packages" / package / name).read_bytes() == (ROOT / name).read_bytes()


@pytest.mark.parametrize("package", LIBRARIES)
def test_a_librarys_shared_fields_are_ffmans(package: str) -> None:
    ffman_file, own_file = (
        _pyproject(ROOT / "packages/ffman"),
        _pyproject(ROOT / "packages" / package),
    )
    ffman, own = _project(ffman_file), _project(own_file)
    assert {f: own[f] for f in SHARED} == {f: ffman[f] for f in SHARED}
    assert own_file["build-system"] == ffman_file["build-system"]
    assert _python_classifiers(own) == _python_classifiers(ffman)
    assert own["license-files"] == list(LICENSES)
    assert own["dependencies"] == []  # the standard library alone


@pytest.mark.parametrize("package", LIBRARIES)
def test_the_licence_expressions_agree(package: str) -> None:
    ffman = _project(_pyproject(ROOT / "packages/ffman"))
    own = _project(_pyproject(ROOT / "packages" / package))
    # ffman's is the libraries' and the fonts': SPDX applies AND before OR, hence the parentheses
    assert ffman["license"] == f"({cast('str', own['license'])}) AND OFL-1.1"


@pytest.mark.parametrize("package", LIBRARIES)
def test_ffmans_range_admits_each_librarys_version(package: str) -> None:
    # uv locks a workspace member without ffman's specifier (measured): a library bumped out of
    # the range still locks, and ffman would be tested on a version its wheel refuses. The
    # release hook (cog.toml) runs this test after the bump
    version = cast("str", _project(_pyproject(ROOT / "packages" / package))["version"])
    ffman = _project(_pyproject(ROOT / "packages/ffman"))
    (requirement,) = (
        r for r in map(Requirement, cast("list[str]", ffman["dependencies"])) if r.name == package
    )
    assert requirement.specifier.contains(version), (str(requirement), version)


def _definitions(module: Path) -> dict[str, str]:
    """A module's top-level definitions by name, as code (comments aside)."""
    found: dict[str, str] = {}
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        match node:
            case (
                ast.FunctionDef(name=name)
                | ast.AsyncFunctionDef(name=name)
                | ast.ClassDef(name=name)
                | ast.TypeAlias(name=ast.Name(id=name))
                | ast.Assign(targets=[ast.Name(id=name)])
                | ast.AnnAssign(target=ast.Name(id=name))
            ):
                found[name] = ast.unparse(node)
            case _:
                pass
    return found


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ("packages/ffman/tests/conftest.py", "packages/ffmeta/tests/conftest.py"),
        ("packages/ffman/tests/support/media.py", "packages/ffmeta/tests/ffmeta_support/media.py"),
    ],
)
def test_ffmetas_oracle_tools_are_ffmans(ours: str, theirs: str) -> None:
    # both trees run the pinned tools (each sdist its own copy): each definition ffmeta's carries is
    # ffman's -- the pins, the CD FLAC, what ffprobe sees -- or the oracles describe two ffmpegs; a
    # name renamed in either tree fails here
    mine, its = _definitions(ROOT / ours), _definitions(ROOT / theirs)
    assert its  # nothing carried proves nothing
    assert its == {name: mine.get(name) for name in its}


@pytest.mark.parametrize("package", PACKAGES)
def test_a_packages_pytest_rules_are_the_roots(package: str) -> None:
    # each its own, for its sdist's tests: every option it sets is the root's, but where its
    # tests are (testpaths, pythonpath: the root's name all three trees)
    def options(folder: Path) -> dict[str, object]:
        tool = cast("dict[str, dict[str, dict[str, object]]]", _pyproject(folder)["tool"])
        return tool["pytest"]["ini_options"]

    own, root = options(ROOT / "packages" / package), options(ROOT)
    rules = own.keys() - {"testpaths", "pythonpath"}
    assert {"addopts", "filterwarnings", "strict"} <= rules
    assert {key: own[key] for key in rules} == {key: root[key] for key in rules}


def _profile(conftest: Path) -> str:
    """A conftest's Hypothesis profile: its register_profile's settings, as written."""
    for node in ast.walk(ast.parse(conftest.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register_profile"
        ):
            return ", ".join(f"{k.arg}={ast.unparse(k.value)}" for k in node.keywords)
    msg = f"no Hypothesis profile in {conftest}"
    raise AssertionError(msg)


def test_the_hypothesis_profiles_are_one() -> None:
    # settings are process-global: in one run from the root the last conftest's loaded profile
    # governs all three trees -- each must be the same, or the run depends on import order
    trees = [ROOT / "packages" / package / "tests" for package in PACKAGES]
    profiles = {tree.relative_to(ROOT).as_posix(): _profile(tree / "conftest.py") for tree in trees}
    assert len(set(profiles.values())) == 1, profiles


# the test files each library carries alike: one rule, written once per package (each sdist runs
# its own), so a fix to one copy must reach the other
SHARED_TESTS: Final = ("test_api.py", "test_imports.py", "test_readme.py")


@pytest.mark.parametrize("name", SHARED_TESTS)
def test_the_libraries_shared_tests_differ_by_their_name_alone(name: str) -> None:
    first, *others = (
        (ROOT / "packages" / package / "tests" / name)
        .read_text(encoding="utf-8")
        .replace(package, "PACKAGE")
        for package in LIBRARIES
    )
    for other in others:
        assert other == first  # pytest prints the lines that differ
