# Albert Thomson, Dylan Burton, Johnathan Greene, Justin Khuu
# Contract Sentinel

# json builds fake Gemini replies, pytest runs the tests
import json
import pytest
# SDK error classes let us simulate real API failures
from google.genai import errors as genai_errors
# Module under test, plus the main workflow
import gemini_client
import main
from gemini_client import GeminiAPIError, analyze_contract, parse_findings

# One well-formed finding, like Gemini should return
GOOD = {
    "vulnerability_type": "reentrancy",
    "function_name": "withdraw",
    "line_number": 12,
    "severity": "High",
    "description": "Sends ETH before updating balance.",
    "recommendation": "Update state before the external call.",
}
CODE = "pragma solidity ^0.8.0;\ncontract A {}\n"


# Make retries instant so tests don't actually wait
@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_client.time, "sleep", lambda s: None)


# Replace the real API call with a fake that returns the given text
def fake_gemini(monkeypatch, text):
    monkeypatch.setattr(gemini_client, "_call_gemini", lambda prompt: text)


# ---------- Test API responses ----------

# Test: a good response becomes a list of findings (severity lowercased)
def test_valid_response(monkeypatch):
    fake_gemini(monkeypatch, json.dumps([GOOD]))
    findings = analyze_contract(CODE)
    assert len(findings) == 1 and findings[0]["severity"] == "high"

# Test: an empty list means "no issues found"
def test_no_findings(monkeypatch):
    fake_gemini(monkeypatch, "[]")
    assert analyze_contract(CODE) == []

# Test: JSON wrapped in ```json fences still parses
def test_markdown_fences_stripped():
    assert len(parse_findings("```json\n" + json.dumps([GOOD]) + "\n```")) == 1

# Test: a {"findings": [...]} wrapper is accepted
def test_wrapped_findings():
    assert len(parse_findings(json.dumps({"findings": [GOOD]}))) == 1

# Test: malformed items are skipped instead of crashing
def test_malformed_items_skipped():
    bad_severity = {**GOOD, "severity": "catastrophic"}
    missing_field = {k: v for k, v in GOOD.items() if k != "description"}
    result = parse_findings(json.dumps([GOOD, bad_severity, missing_field, "junk"]))
    assert len(result) == 1

# Test: the contract source is included in the prompt sent to Gemini
def test_prompt_contains_source(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini_client, "_call_gemini", lambda p: seen.setdefault("p", p) and "[]")
    analyze_contract(CODE)
    assert "contract A {}" in seen["p"]


# ---------- API error handling ----------

# Test: invalid JSON gives a clear error
def test_invalid_json(monkeypatch):
    fake_gemini(monkeypatch, "not json at all")
    with pytest.raises(GeminiAPIError, match="invalid JSON"):
        analyze_contract(CODE)

# Test: JSON that isn't a list gives a clear error
def test_not_a_list():
    with pytest.raises(GeminiAPIError, match="not a JSON list"):
        parse_findings('"hello"')

# Test: a missing API key gives a clear setup message
def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiAPIError, match="Missing API key"):
        analyze_contract(CODE)

# Make a fake _call_gemini that raises the given errors, then succeeds
def flaky(monkeypatch, errors):
    calls = {"n": 0}
    def fake(prompt):
        calls["n"] += 1
        if calls["n"] <= len(errors):
            raise errors[calls["n"] - 1]
        return "[]"
    monkeypatch.setattr(gemini_client, "_call_gemini", fake)
    return calls

# Test: a rate-limit error is retried and then succeeds
def test_retries_rate_limit(monkeypatch):
    calls = flaky(monkeypatch, [genai_errors.ClientError(429, {"error": {"message": "q"}})])
    assert analyze_contract(CODE) == [] and calls["n"] == 2

# Test: a server error is retried and then succeeds
def test_retries_server_error(monkeypatch):
    calls = flaky(monkeypatch, [genai_errors.ServerError(503, {"error": {"message": "x"}})])
    assert analyze_contract(CODE) == [] and calls["n"] == 2

# Test: a timeout is retried and then succeeds
def test_retries_timeout(monkeypatch):
    calls = flaky(monkeypatch, [TimeoutError()])
    assert analyze_contract(CODE) == [] and calls["n"] == 2

# Test: after 3 failed attempts we give up with a clear error
def test_gives_up_after_max_attempts(monkeypatch):
    err = genai_errors.ServerError(500, {"error": {"message": "x"}})
    calls = flaky(monkeypatch, [err, err, err, err])
    with pytest.raises(GeminiAPIError, match="server error"):
        analyze_contract(CODE)
    assert calls["n"] == 3

# Test: bad-key errors are NOT retried
def test_auth_error_not_retried(monkeypatch):
    err = genai_errors.ClientError(403, {"error": {"message": "bad key"}})
    calls = flaky(monkeypatch, [err, err])
    with pytest.raises(GeminiAPIError, match="Authentication failed"):
        analyze_contract(CODE)
    assert calls["n"] == 1

# Test: an invalid request (400) is NOT retried
def test_bad_request_not_retried(monkeypatch):
    err = genai_errors.ClientError(400, {"error": {"message": "bad"}})
    calls = flaky(monkeypatch, [err, err])
    with pytest.raises(GeminiAPIError, match="rejected the request"):
        analyze_contract(CODE)
    assert calls["n"] == 1


# ---------- Main workflow ----------

# Test: main.run_audit reads the file and returns Gemini's findings
def test_run_audit(monkeypatch, tmp_path):
    f = tmp_path / "c.sol"
    f.write_text(CODE)
    fake_gemini(monkeypatch, json.dumps([GOOD]))
    assert main.run_audit(str(f))[0]["vulnerability_type"] == "reentrancy"


# ---------- Interactions API specifics (v1beta and its error types) ----------

# Fake versions of the Interactions API errors (same names and attributes as the SDK's)
class BadRequestError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.status_code = 400
        self.message = message

class RateLimitError(Exception):
    status_code = 429
    message = "quota"

class APIConnectionError(Exception):
    pass

# Test: the real call asks for v1beta, JSON output, and a response format
def test_call_uses_v1beta(monkeypatch):
    seen = {}
    class FakeInteractions:
        def create(self, **kwargs):
            seen.update(kwargs)
            class Reply:
                output_text = "[]"
            return Reply()
    class FakeClient:
        interactions = FakeInteractions()
    monkeypatch.setattr(gemini_client, "_create_client", lambda: FakeClient())
    assert gemini_client._call_gemini("hi") == "[]"
    assert seen["api_version"] == "v1beta"
    assert seen["response_mime_type"] == "application/json"
    # response_format must be set too, with the schema inside it
    assert seen["response_format"]["mime_type"] == "application/json"
    assert seen["response_format"]["schema"] == gemini_client.RESPONSE_SCHEMA

# Test: an Interactions 400 error is reported as a rejected request, not a network error
def test_interactions_400_not_labeled_network(monkeypatch):
    err = BadRequestError("field not allowed")
    calls = flaky(monkeypatch, [err, err])
    with pytest.raises(GeminiAPIError, match="rejected the request.*field not allowed"):
        analyze_contract(CODE)
    assert calls["n"] == 1

# Test: an Interactions 429 error is retried
def test_interactions_429_retried(monkeypatch):
    calls = flaky(monkeypatch, [RateLimitError()])
    assert analyze_contract(CODE) == [] and calls["n"] == 2

# Test: an Interactions connection error is retried
def test_interactions_connection_error_retried(monkeypatch):
    calls = flaky(monkeypatch, [APIConnectionError("Connection error.")])
    assert analyze_contract(CODE) == [] and calls["n"] == 2

# Test: a persistent connection error is reported as a network error
def test_connection_error_message(monkeypatch):
    err = APIConnectionError("Connection error.")
    flaky(monkeypatch, [err, err, err])
    with pytest.raises(GeminiAPIError, match="Network error"):
        analyze_contract(CODE)

# Test: an unknown error type is labeled "unexpected", not "network"
def test_unknown_error_labeled_unexpected(monkeypatch):
    flaky(monkeypatch, [ValueError("weird")])
    with pytest.raises(GeminiAPIError, match="Unexpected error"):
        analyze_contract(CODE)
