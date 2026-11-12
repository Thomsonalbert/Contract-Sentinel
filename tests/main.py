# Albert Thomson, Dylan Burton, Johnathan Greene, Justin Khuu
# Contract Sentinel
"""Main workflow: read a Solidity file, then get Gemini's candidate findings.
Slither comparison will be added after this step.
"""

# json prints the findings, sys handles CLI args and exit codes
import json
import sys
# Our own modules for each step of the pipeline
from file_input import SolidityFileError, read_solidity_file
from gemini_client import GeminiAPIError, analyze_contract


# Run the pipeline for one contract and return Gemini's candidate findings
def run_audit(file_path: str) -> list[dict]:
    # Step 1: read and validate the Solidity file
    source_code = read_solidity_file(file_path)
    # Step 2: ask Gemini for candidate vulnerabilities
    return analyze_contract(source_code)


# Command-line entry point:  python main.py contract.sol
def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python main.py <path-to-contract.sol>")
        return 1
    try:
        findings = run_audit(sys.argv[1])
    # Either module's failure ends up here as a readable message
    except (SolidityFileError, GeminiAPIError) as err:
        print(f"Error: {err}")
        return 1
    print(json.dumps(findings, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
