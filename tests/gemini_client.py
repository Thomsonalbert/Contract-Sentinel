# Albert Thomson, Dylan Burton, Johnathan Greene, Justin Khuu
# Contract Sentinel
"""Gemini API integration for Contract Sentinel.
Sends Solidity source code to Gemini and returns candidate vulnerabilities
as a list of dicts, ready to be compared against Slither's findings.
"""

# Lets us use the "str | None" type hint syntax cleanly
from __future__ import annotations
# json parses Gemini's response, os reads the API key, sys handles CLI args
import json
import os
import sys
# time.sleep is used for the retry backoff
import time
# Official Gemini SDK
from google import genai

# Model name lives here so it is easy to change and pin for reproducibility
GEMINI_MODEL = "gemini-3.8-flash"
# response_mime_type is only available on the v1beta API version
API_VERSION = "v1beta"
# Environment variable that holds the API key (never hardcode the key)
API_KEY_ENV_VAR = "GEMINI_API_KEY"
# How many times to try before giving up on a temporary error
MAX_ATTEMPTS = 3
# Seconds to wait before the first retry (doubles each time)
BASE_BACKOFF_SECONDS = 2.0
# Low temperature keeps results more repeatable
TEMPERATURE = 0.1
# Fields every finding must contain
REQUIRED_FIELDS = (
    "vulnerability_type",
    "function_name",
    "line_number",
    "severity",
    "description",
    "recommendation",
)
# Severity values we accept
VALID_SEVERITIES = {"high", "medium", "low", "informational"}

# JSON schema that tells Gemini exactly what shape the reply must have
RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "vulnerability_type": {"type": "string"},
            "function_name": {"type": "string"},
            "line_number": {"type": "integer"},
            "severity": {
                "type": "string",
                "enum": ["high", "medium", "low", "informational"],
            },
            "description": {"type": "string"},
            "recommendation": {"type": "string"},
        },
        "required": list(REQUIRED_FIELDS),
    },
}

# Instructions sent to Gemini along with the contract
PROMPT_TEMPLATE = """You are a smart-contract security auditor.
Analyze the Solidity contract below and list candidate security vulnerabilities.
Base your findings only on the code provided.

Return ONLY a JSON list. Each item must have exactly these fields:
- "vulnerability_type": short name, e.g. "reentrancy", "access control", "unchecked call"
- "function_name": the function containing the issue
- "line_number": best-estimate integer line number, or 0 if unknown
- "severity": one of "high", "medium", "low", "informational"
- "description": one or two sentences
- "recommendation": one sentence

If you find no issues, return an empty list: []

Solidity contract:
```solidity
{source_code}
```
"""


# Custom error type so the rest of the program only needs one except clause
class GeminiAPIError(Exception):
    """Raised for any failure when calling Gemini or reading its response."""


# Build the Gemini client, failing clearly if the key is missing
def _create_client() -> genai.Client:
    # Read the key from the environment
    api_key = os.environ.get(API_KEY_ENV_VAR)
    # A missing or blank key is a setup problem, so say so plainly
    if not api_key or not api_key.strip():
        raise GeminiAPIError(
            f"Missing API key. Set the {API_KEY_ENV_VAR} environment variable."
        )
    return genai.Client(api_key=api_key)


# The only function that talks to Gemini, kept small so tests can mock it
def _call_gemini(prompt: str) -> str:
    """Send the prompt to Gemini and return the raw response text."""
    client = _create_client()
    # No google_search tool: the audit should rely only on the code provided
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        generation_config={"temperature": TEMPERATURE},
        # Gemini requires response_format whenever response_mime_type is set
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": RESPONSE_SCHEMA,
        },
        response_mime_type="application/json",
        api_version=API_VERSION,
    )
    # output_text is the combined text of the model's reply
    text = interaction.output_text
    # An empty reply (for example a blocked response) is treated as an error
    if not text or not text.strip():
        raise GeminiAPIError("Gemini returned an empty or blocked response.")
    return text


# Get the HTTP status from either kind of SDK error (or None if there isn't one)
def _status_code(exc: Exception) -> int | None:
    # The Interactions API raises errors that use "status_code",
    # while the older SDK errors use "code", so check both
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


# Detect network problems and timeouts, whichever library raised them
def _is_connection_error(exc: Exception) -> bool:
    # Python's own errors, plus the class names the SDK and httpx use
    names = {cls.__name__ for cls in type(exc).__mro__}
    connection_names = {
        "ConnectionError", "TimeoutError", "APIConnectionError",
        "APITimeoutError", "ConnectError", "TimeoutException",
    }
    return bool(names & connection_names)


# Decide whether an error is worth retrying
def _is_retryable(exc: Exception) -> bool:
    status = _status_code(exc)
    # 429 (rate limit) and 5xx (server) errors are usually temporary
    if status is not None:
        return status == 429 or status >= 500
    # Network problems and timeouts are also usually temporary
    return _is_connection_error(exc)


# Turn an SDK error into a readable GeminiAPIError message
def _describe_error(exc: Exception) -> str:
    status = _status_code(exc)
    if status is not None:
        # 401/403 almost always means a bad or unauthorized key
        if status in (401, 403):
            return f"Authentication failed (HTTP {status}). Check your API key."
        if status == 429:
            return "Rate limit or quota exceeded (HTTP 429)."
        if status >= 500:
            return f"Gemini server error (HTTP {status})."
        # Any other status is a problem with our request, so show Gemini's message
        message = getattr(exc, "message", None) or str(exc)
        return f"Gemini rejected the request (HTTP {status}): {message}"
    if _is_connection_error(exc):
        return f"Network error while contacting Gemini: {exc}"
    # Anything else is unexpected, so don't mislabel it as a network problem
    return f"Unexpected error while calling Gemini: {type(exc).__name__}: {exc}"


# Call Gemini with retries and exponential backoff for temporary errors
def _call_with_retries(prompt: str) -> str:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _call_gemini(prompt)
        # Our own errors (missing key, empty reply) are not retried
        except GeminiAPIError:
            raise
        except Exception as exc:
            # Give up on permanent errors or when attempts run out
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS:
                raise GeminiAPIError(_describe_error(exc)) from exc
            # Wait 2s, then 4s, ... before trying again
            time.sleep(BASE_BACKOFF_SECONDS * 2 ** (attempt - 1))
    # Unreachable, but keeps type checkers happy
    raise GeminiAPIError("Gemini call failed.")


# Convert Gemini's text reply into a validated list of findings
def parse_findings(response_text: str) -> list[dict]:
    """Parse the JSON reply and keep only well-formed findings."""
    # Strip ```json fences in case the model added them anyway
    cleaned = response_text.strip().removeprefix("```json").removeprefix("```")
    cleaned = cleaned.removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiAPIError(f"Gemini returned invalid JSON: {exc}") from exc
    # Some models wrap the list in an object, so accept {"findings": [...]}
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        data = data["findings"]
    if not isinstance(data, list):
        raise GeminiAPIError("Gemini response was not a JSON list.")

    findings = []
    for item in data:
        # Skip anything that is not an object with all required fields
        if not isinstance(item, dict) or any(f not in item for f in REQUIRED_FIELDS):
            continue
        # Normalize severity so later comparisons are consistent
        severity = str(item["severity"]).strip().lower()
        if severity not in VALID_SEVERITIES:
            continue
        findings.append({**item, "severity": severity})
    return findings


# Main function: Solidity source in, candidate findings out
def analyze_contract(source_code: str) -> list[dict]:
    """Ask Gemini for candidate vulnerabilities in the given Solidity code.
    Args:
        source_code: Solidity source (from file_input.read_solidity_file).
    Returns:
        A list of finding dicts (empty if Gemini found no issues).
    Raises:
        GeminiAPIError: for any API, network, or response-format failure.
    """
    # Fill the contract into the prompt, then call Gemini with retries
    prompt = PROMPT_TEMPLATE.format(source_code=source_code)
    response_text = _call_with_retries(prompt)
    return parse_findings(response_text)


# Runs only when executed directly:  python gemini_client.py contract.sol
if __name__ == "__main__":
    # Imported here so the module has no hard dependency on file_input
    from file_input import SolidityFileError, read_solidity_file

    if len(sys.argv) != 2:
        sys.exit("Usage: python gemini_client.py <path-to-contract.sol>")
    try:
        results = analyze_contract(read_solidity_file(sys.argv[1]))
    except (SolidityFileError, GeminiAPIError) as err:
        sys.exit(f"Error: {err}")
    print(json.dumps(results, indent=2))
