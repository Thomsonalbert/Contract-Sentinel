# Albert Thomson, Dylan Burton, Johnathan Greene, Justin Khuu
# Contract Sentinel
"""File-input logic for Contract Sentinel.
Reads a Solidity (.sol) file from disk, validates it, and returns its source
code so the LLM module and Slither can analyze it later.
"""

# Lets us use the "str | Path" type hint syntax cleanly
from __future__ import annotations
# re is used to strip comments and look for contract declarations
import re
# sys gives us command-line arguments and a way to exit with a message
import sys
# Path handles file paths in a way that works on Windows, Mac, and Linux
from pathlib import Path

# Largest file we accept (1 MB), real contracts are far smaller than this
MAX_FILE_SIZE_BYTES = 1_000_000

# Matches /* block comments */ and // line comments
_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
# Matches a top-level contract, interface, or library declaration
_DECLARATION_RE = re.compile(r"\b(?:contract|interface|library)\s+[A-Za-z_]\w*")


# Custom error type so callers only need to catch one kind of exception
class SolidityFileError(Exception):
    """Raised when a Solidity file cannot be loaded or fails validation.
    Every file-related failure is converted into this one exception type,
    so the rest of the program only needs a single `except` clause.
    """


# Check that the text actually looks like Solidity (not just any .sol file)
def validate_solidity_source(source_code: str, source_name: str = "file") -> None:
    """Raise SolidityFileError if the text does not look like Solidity.
    This is a light sanity check, not a compiler: it confirms the code
    declares at least one contract, interface, or library outside comments.
    """
    # Remove comments so a contract named only in a comment doesn't count
    code_without_comments = _COMMENT_RE.sub("", source_code)
    # No declaration found means this is probably not a real Solidity file
    if not _DECLARATION_RE.search(code_without_comments):
        raise SolidityFileError(
            f"{source_name} does not look like Solidity: "
            "no contract, interface, or library declaration found."
        )


# Main function: takes a file path and returns the Solidity source as a string
def read_solidity_file(file_path: str | Path) -> str:
    """Read and validate a .sol file, then return its contents as a string.
    Args:
        file_path: Path to a Solidity source file (e.g. "contract.sol").
    Returns:
        The Solidity source code as a string.
    Raises:
        SolidityFileError: if the file is missing, is not a .sol file, is a
            directory, is too large, cannot be read, is not valid UTF-8 text,
            is empty, or does not contain a contract declaration.
    """
    # Convert the input to a Path object and expand "~" to the home folder
    path = Path(file_path).expanduser()

    # Reject anything that isn't a .sol file (case-insensitive)
    if path.suffix.lower() != ".sol":
        raise SolidityFileError(
            f"Expected a .sol file, but got '{path.name}' "
            f"(extension: '{path.suffix or 'none'}')."
        )
    # Reject paths that don't exist on disk
    if not path.exists():
        raise SolidityFileError(f"File not found: {path}")
    # Reject folders that happen to be named like a .sol file
    if not path.is_file():
        raise SolidityFileError(f"Path is not a file: {path}")
    # Reject huge files before loading them into memory
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise SolidityFileError(
            f"File is too large (limit is {MAX_FILE_SIZE_BYTES} bytes): {path}"
        )

    try:
        # utf-8-sig silently strips a BOM if an editor added one
        source_code = path.read_text(encoding="utf-8-sig")
    # The OS won't let us open the file
    except PermissionError:
        raise SolidityFileError(f"Permission denied when reading: {path}") from None
    # The file contains bytes that aren't valid UTF-8 text
    except UnicodeDecodeError:
        raise SolidityFileError(f"File is not valid UTF-8 text: {path}") from None
    # Catch-all for any other read problem, keeping the original error attached
    except OSError as exc:
        raise SolidityFileError(f"Could not read {path}: {exc}") from exc

    # Reject files that are blank or contain only whitespace
    if not source_code.strip():
        raise SolidityFileError(f"File is empty: {path}")

    # Reject files that don't contain any Solidity declaration
    validate_solidity_source(source_code, source_name=path.name)

    # Success: hand the Solidity code back to the caller
    return source_code


# This block only runs when the file is executed directly, not when imported
if __name__ == "__main__":
    # Quick manual check:  python file_input.py path/to/contract.sol
    # Require exactly one argument: the path to the .sol file
    if len(sys.argv) != 2:
        sys.exit("Usage: python file_input.py <path-to-contract.sol>")
    try:
        # sys.argv[1] is the file path the user typed
        code = read_solidity_file(sys.argv[1])
    # Print a friendly message instead of a long traceback
    except SolidityFileError as err:
        sys.exit(f"Error: {err}")
    # Show how much code was loaded as a quick sanity check
    print(f"Loaded {len(code.splitlines())} lines, {len(code)} characters.")
