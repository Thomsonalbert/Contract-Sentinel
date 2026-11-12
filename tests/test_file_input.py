# Albert Thomson, Dylan Burton, Johnathan Greene, Justin Khuu
# Contract Sentinel

# pytest runs the tests and lets us check that errors are raised
import pytest
# Path lets us find the sample contracts next to this test file
from pathlib import Path
# Import the module itself (to change its size limit) and the code being tested
import file_input
from file_input import SolidityFileError, read_solidity_file

# Small valid Solidity snippet used as test data
SAMPLE = "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\ncontract A {}\n"
# Folder holding real sample contracts for the "supported files" tests
SAMPLES_DIR = Path(__file__).parent / "samples"


# ---------- Supported Solidity files ----------

# Test: a valid .sol file is read back exactly as written
def test_reads_valid_file(tmp_path):
    f = tmp_path / "contract.sol"
    f.write_text(SAMPLE, encoding="utf-8")
    assert read_solidity_file(f) == SAMPLE

# Test: the function also works when the path is given as a plain string
def test_accepts_string_path(tmp_path):
    f = tmp_path / "contract.sol"
    f.write_text(SAMPLE, encoding="utf-8")
    assert read_solidity_file(str(f)) == SAMPLE

# Test: an uppercase .SOL extension is still accepted
def test_uppercase_extension(tmp_path):
    f = tmp_path / "CONTRACT.SOL"
    f.write_text(SAMPLE, encoding="utf-8")
    assert read_solidity_file(f) == SAMPLE

# Test: interfaces and libraries count as valid Solidity too
@pytest.mark.parametrize("keyword", ["interface", "library", "contract"])
def test_accepts_all_declaration_types(tmp_path, keyword):
    f = tmp_path / "thing.sol"
    f.write_text(f"pragma solidity ^0.8.0;\n{keyword} Thing {{}}\n")
    assert keyword in read_solidity_file(f)

# Test: a leading BOM (added by some Windows editors) is stripped
def test_bom_is_stripped(tmp_path):
    f = tmp_path / "bom.sol"
    f.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
    assert read_solidity_file(f) == SAMPLE

# Test: Windows line endings (\r\n) come back as plain \n
def test_windows_line_endings(tmp_path):
    f = tmp_path / "crlf.sol"
    f.write_bytes(SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    assert "\r" not in read_solidity_file(f)

# Test: every real sample contract in samples/ loads successfully
@pytest.mark.parametrize("sample", sorted(SAMPLES_DIR.glob("*.sol")), ids=lambda p: p.name)
def test_real_sample_contracts(sample):
    code = read_solidity_file(sample)
    assert "pragma solidity" in code


# ---------- Invalid files and file handling ----------

# Test: a file that doesn't exist raises a "not found" error
def test_missing_file(tmp_path):
    # The with-block passes only if the expected error is raised
    with pytest.raises(SolidityFileError, match="not found"):
        read_solidity_file(tmp_path / "nope.sol")

# Test: a file without the .sol extension is rejected
def test_wrong_extension(tmp_path):
    f = tmp_path / "contract.txt"
    f.write_text(SAMPLE)
    with pytest.raises(SolidityFileError, match=r"\.sol"):
        read_solidity_file(f)

# Test: a file with no extension at all is rejected
def test_no_extension(tmp_path):
    f = tmp_path / "contract"
    f.write_text(SAMPLE)
    with pytest.raises(SolidityFileError, match="none"):
        read_solidity_file(f)

# Test: a directory is rejected even if its name ends in .sol
def test_directory(tmp_path):
    d = tmp_path / "folder.sol"
    d.mkdir()
    with pytest.raises(SolidityFileError, match="not a file"):
        read_solidity_file(d)

# Test: a file containing only whitespace counts as empty
def test_empty_file(tmp_path):
    f = tmp_path / "empty.sol"
    f.write_text("   \n")
    with pytest.raises(SolidityFileError, match="empty"):
        read_solidity_file(f)

# Test: a file with bytes that aren't valid UTF-8 is rejected
def test_invalid_encoding(tmp_path):
    f = tmp_path / "bad.sol"
    f.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(SolidityFileError, match="UTF-8"):
        read_solidity_file(f)

# Test: a file over the size limit is rejected
def test_file_too_large(tmp_path, monkeypatch):
    # Shrink the limit for this test so we don't need a huge file
    monkeypatch.setattr(file_input, "MAX_FILE_SIZE_BYTES", 10)
    f = tmp_path / "big.sol"
    f.write_text(SAMPLE)
    with pytest.raises(SolidityFileError, match="too large"):
        read_solidity_file(f)


# ---------- File validation checks ----------

# Test: a .sol file with plain text instead of code is rejected
def test_not_solidity_content(tmp_path):
    f = tmp_path / "notes.sol"
    f.write_text("hello, this is not a smart contract")
    with pytest.raises(SolidityFileError, match="does not look like Solidity"):
        read_solidity_file(f)

# Test: a contract that only appears inside comments doesn't count
def test_declaration_only_in_comments(tmp_path):
    f = tmp_path / "commented.sol"
    f.write_text("// contract A {}\n/* contract B {} */\npragma solidity ^0.8.0;\n")
    with pytest.raises(SolidityFileError, match="does not look like Solidity"):
        read_solidity_file(f)
