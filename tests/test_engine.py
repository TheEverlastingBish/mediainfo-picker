import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from mediainfo_picker.engine import (
    Field,
    MediaInfo,
    MediaInfoError,
    Mode,
    command_line,
    parse_fields,
    parse_info_parameters,
    plan,
    strip_params,
)

FX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FX / name).read_text()


@pytest.fixture(scope="module")
def fields() -> list[Field]:
    return parse_fields(read("full.txt"), read("full-raw.txt"), read("default-raw.txt"))


@pytest.fixture(scope="module")
def known() -> set[str]:
    return parse_info_parameters(read("info-parameters.txt"))


def by(fields: list[Field], param: str, section: str | None = None) -> Field:
    return next(f for f in fields if f.param == param and (section is None or f.section == section))


# --- reading fields -------------------------------------------------------------------------------


def test_every_full_line_becomes_a_field(fields: list[Field]) -> None:
    lines = [ln for ln in read("full.txt").splitlines() if " : " in ln]
    assert len(fields) == len(lines)


def test_raw_names_and_labels_are_paired(fields: list[Field]) -> None:
    f = by(fields, "General_VideoCount")
    assert f.label == "Count of video streams" and f.section == "General"
    assert by(fields, "General_Title").value == "Sample Title"


def test_default_flag_comes_from_the_plain_output(fields: list[Field]) -> None:
    assert by(fields, "General_Format/String").default
    assert not by(fields, "General_Format").default  # only the /String variant is shown
    assert not by(fields, "General_VideoCount").default


def test_sections_are_numbered_per_stream(fields: list[Field]) -> None:
    assert {f.section for f in fields if f.kind == "Audio"} == {"Audio #1", "Audio #2"}


def test_attachments_is_read_although_mediainfo_does_not_list_it(fields: list[Field], known: set[str]) -> None:
    f = by(fields, "General_Attachments")
    assert f.default and f.value == "cover.jpg"
    assert "General_Attachments" not in known
    assert "General_VideoCount" in known


def test_mismatched_outputs_fail_loudly() -> None:
    with pytest.raises(MediaInfoError):
        parse_fields(read("full.txt"), read("default-raw.txt"), read("default-raw.txt"))


# --- planning -------------------------------------------------------------------------------------


def test_default_and_full_modes(fields: list[Field], known: set[str]) -> None:
    assert plan(Mode.DEFAULT, fields, set(), known).args == []
    assert plan(Mode.FULL, fields, set(), known).args == ["--Full"]


def test_selected_hides_unticked_defaults_and_shows_ticked_extras(fields: list[Field], known: set[str]) -> None:
    default = {f.param for f in fields if f.default}
    sel = (default - {"General_Title"}) | {"General_VideoCount"}
    p = plan(Mode.SELECTED, fields, sel, known)
    assert p.args == ["--HideParameter=General_Title", "--ShowParameter=General_VideoCount"]
    assert not p.remove and not p.unshowable


def test_selected_with_every_default_ticked_needs_no_flags(fields: list[Field], known: set[str]) -> None:
    default = {f.param for f in fields if f.default}
    assert plan(Mode.SELECTED, fields, default, known).args == []


def test_unknown_field_is_removed_after_the_run_not_passed(fields: list[Field], known: set[str]) -> None:
    default = {f.param for f in fields if f.default}
    p = plan(Mode.SELECTED, fields, default - {"General_Attachments"}, known)
    assert p.args == [] and p.remove == {"General_Attachments"}


def test_unknown_hidden_field_ticked_is_reported_unshowable(known: set[str]) -> None:
    fs = [Field("General", "Mystery", "Mystery", "x", default=False)]
    p = plan(Mode.SELECTED, fs, {"General_Mystery"}, known)
    assert p.unshowable == ["General_Mystery"] and p.args == []


# --- stripping and the command line ---------------------------------------------------------------


def test_strip_only_touches_the_named_kind() -> None:
    text = "General\nTitle    : a\nEncoded  : x\n\nVideo\nTitle    : b\nEncoded  : y\n"
    raw = "General\nTitle    : a\nEnc_Date : x\n\nVideo\nTitle    : b\nEnc_Date : y\n"
    out, labels = strip_params(text, raw, {"General_Enc_Date"})
    assert out == "General\nTitle    : a\n\nVideo\nTitle    : b\nEncoded  : y\n"
    assert labels == ["General: Encoded"]


@pytest.mark.parametrize("path", ["plain.mkv", "with space.mkv", 'it\'s "quoted".mkv', "$HOME and `x`.mkv"])
def test_command_quotes_any_path(path: str) -> None:
    cmd = command_line("mediainfo", ["--HideParameter=General_Title"], path, [])
    assert shlex.split(cmd) == ["mediainfo", "--HideParameter=General_Title", path]


def test_command_filter_is_section_aware() -> None:
    cmd = command_line("mediainfo", [], "f.mkv", ["General: Encoded date"])
    assert "| awk " in cmd and "General( #[0-9]+)?$" in cmd and "^Encoded date +: " in cmd


# --- against the real mediainfo, when installed ---------------------------------------------------

needs_mediainfo = pytest.mark.skipif(not shutil.which("mediainfo"), reason="mediainfo not installed")


@needs_mediainfo
def test_live_render_matches_its_own_command(tmp_path: Path) -> None:
    sample = tmp_path / "it's a sample.mkv"
    sample.write_bytes((FX / "sample.mkv").read_bytes())
    mi = MediaInfo()
    fields = mi.read_fields(sample)
    default = {f.param for f in fields if f.default}
    sel = (default - {"General_Title", "General_Attachments", "Video_Encoded_Library_Settings"}) | {
        "General_VideoCount"
    }
    result = mi.render(sample, plan(Mode.SELECTED, fields, sel, mi.known_params()))
    assert "Attachments" not in result.text and "Sample Title" not in result.text
    assert "Count of video streams" in result.text
    shell = subprocess.run(["bash", "-c", result.command], capture_output=True, text=True, check=True)
    assert shell.stdout == result.text


@needs_mediainfo
def test_missing_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(MediaInfoError):
        MediaInfo().read_fields(tmp_path / "nope.mkv")


def test_descriptions_are_bundled() -> None:
    from mediainfo_picker.descriptions import data_tag, describe

    assert data_tag().startswith("v")
    assert describe("General_UniqueID/String").startswith("The unique ID")
    assert describe("General_Attachments") == ""
