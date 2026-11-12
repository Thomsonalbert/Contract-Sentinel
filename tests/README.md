# Contract Sentinel

**Hybrid AI-Assisted Security Auditor for Smart Contracts**
VCU College of Engineering capstone (CS 27-326), Fall 2026 to Spring 2027.

Contract Sentinel finds security problems in Solidity smart contracts by combining an LLM (Google Gemini) with a traditional static analyzer (Slither). The LLM reads a contract and proposes *candidate* vulnerabilities, Slither analyzes the same contract independently, and the results are compared. A candidate backed by Slither evidence is **Verified**; one without support is **Unconfirmed**.

**Team:** Albert Thomson, Justin Khuu, Jonathan Greene, Dylan Burton
**Advisor:** Hong-Sheng Zhou

## Project status

| Component | Status |
|---|---|
| Solidity file input and validation (`file_input.py`) | Done |
| Gemini API integration and error handling (`gemini_client.py`) | Done |
| Main workflow: file -> Gemini findings (`main.py`) | Done |
| Slither integration | Planned |
| Comparison and verification of findings (Verified / Unconfirmed) | Planned |
| Evidence-based report generator | Planned |
| Evaluation on SmartBugs (Slither-only vs LLM-only vs hybrid) | Planned |

## Project structure

```
contractsentinal-dev/
  file_input.py          Reads and validates a .sol file
  gemini_client.py       Sends the contract to Gemini, returns candidate findings
  main.py                Command-line entry point that runs the pipeline
  test_file_input.py     Tests for file input and validation
  test_gemini_client.py  Tests for the Gemini client (no real API calls)
  samples/               Example contracts used by the tests
    VulnerableBank.sol   Intentionally vulnerable (reentrancy), for testing only
    samplesol.sol
  requirements.txt       Python dependencies
  .gitignore
```

`main.py` imports `file_input.py` and `gemini_client.py`, so all three must stay in the same folder.

## Requirements

- Python 3.11 or later
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- Internet access (for the Gemini call)

## Setup

1. Clone the repo and open the folder:
   ```bash
   git clone https://github.com/Thomsonalbert/contractsentinal-dev.git
   cd contractsentinal-dev
   ```
2. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate          # Windows
   source venv/bin/activate       # macOS / Linux
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set your API key as an environment variable. The key is read from `GEMINI_API_KEY` and is **never** stored in the code.
   ```powershell
   # Windows PowerShell (lasts for this terminal window only)
   $env:GEMINI_API_KEY = "your-key-here"
   ```
   ```bash
   # macOS / Linux
   export GEMINI_API_KEY="your-key-here"
   ```

Each team member should use their own key.

## Usage

Run the pipeline on a Solidity file:

```bash
python main.py samples/VulnerableBank.sol
```

You can also run each stage on its own:

```bash
python file_input.py samples/VulnerableBank.sol      # read and validate only
python gemini_client.py samples/VulnerableBank.sol   # file -> Gemini findings
```

A run takes roughly 5 to 20 seconds, almost all of it waiting for Gemini.

### Example output

```json
[
  {
    "vulnerability_type": "reentrancy",
    "function_name": "withdraw",
    "line_number": 14,
    "severity": "high",
    "description": "The function transfers Ether to the caller via an external call before updating the user balance in storage, exposing the contract to reentrancy attacks.",
    "recommendation": "Apply the Checks-Effects-Interactions pattern by setting the balance to zero before initiating the external transfer, or protect the function with a reentrancy guard."
  }
]
```

An empty list (`[]`) means Gemini found no issues.

### Finding format

Every finding is a dict with these fields, shared with the planned Slither output so the two can be compared.

| Field | Meaning |
|---|---|
| `vulnerability_type` | Short name, e.g. `reentrancy`, `access control` |
| `function_name` | Function containing the issue |
| `line_number` | Best-estimate line number (`0` means unknown) |
| `severity` | `high`, `medium`, `low`, or `informational` |
| `description` | One or two sentences |
| `recommendation` | One sentence |

## Running the tests

```bash
pytest
```

The tests use mocked Gemini responses, so they need no API key and make no network calls. If the `samples/` folder is missing, the real-contract tests are skipped.

## How it works

1. **File input** (`file_input.py`): `read_solidity_file(path)` checks the path, then returns the source as a string. It rejects non-`.sol` files, missing files, directories, files over 1 MB, non-UTF-8 files, empty files, and files with no `contract`, `interface`, or `library` declaration. All failures raise `SolidityFileError`.
2. **Gemini analysis** (`gemini_client.py`): `analyze_contract(source)` sends the code to Gemini with an auditor prompt and a JSON schema, then validates the reply. Malformed findings are skipped instead of crashing. All failures raise `GeminiAPIError`.
3. **Main workflow** (`main.py`): `run_audit(path)` runs both steps and prints the findings.

### Error handling

Temporary errors (rate limit 429, server errors 5xx, timeouts, network problems) are retried up to 3 times, waiting 2 seconds then 4 seconds. Permanent errors are not retried and give a clear message.

| Situation | Message |
|---|---|
| `GEMINI_API_KEY` not set | `Missing API key. Set the GEMINI_API_KEY environment variable.` |
| Bad or unauthorized key (401/403) | `Authentication failed...` |
| Rate limit (429) | `Rate limit or quota exceeded...` |
| Server error (5xx) | `Gemini server error...` |
| Invalid request (400) | `Gemini rejected the request...` plus Gemini's message |
| Empty or blocked reply | `Gemini returned an empty or blocked response.` |
| Reply is not valid JSON | `Gemini returned invalid JSON...` |

### Configuration

Settings are constants at the top of `gemini_client.py`:

| Constant | Default | Purpose |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model name (pin it for reproducible results) |
| `API_VERSION` | `v1beta` | Needed for JSON-output settings |
| `TEMPERATURE` | `0.1` | Low value for more repeatable output |
| `MAX_ATTEMPTS` | `3` | Tries before giving up on a temporary error |
| `BASE_BACKOFF_SECONDS` | `2.0` | First retry wait (doubles each time) |

## Troubleshooting

- **`ModuleNotFoundError: No module named 'file_input'`**: Python can't find the file. Make sure `file_input.py`, `gemini_client.py`, and `main.py` are in the same folder and named exactly that (downloads sometimes become `file_input (1).py`). Run the command from inside that folder.
- **`Missing API key`**: set `GEMINI_API_KEY` in the same terminal window you run the command from.
- **`Authentication failed`**: the key is wrong or was deleted. Create a new one in AI Studio.
- **Gemini rejected the request (400)**: copy the full message. It usually names the setting to change.

## Security

- Never commit an API key. Keep keys in the environment variable only, and never put them in code, a `.env` file that gets committed, or chat messages.
- If a key is ever exposed, delete it in AI Studio and create a new one.
- `samples/VulnerableBank.sol` is intentionally vulnerable. Use it for testing only and never deploy it.

## Scope

Contract Sentinel does security analysis only. It does not execute transactions, exploit deployed contracts, or apply automatic patches. It targets Solidity contracts for the Ethereum Virtual Machine, and it uses existing LLMs through their API without training a custom model. It cannot guarantee that every vulnerability is found or that all false positives are removed.

## Roadmap

1. Slither wrapper that returns findings in the same format
2. Comparison module that marks LLM findings as Verified or Unconfirmed
3. Evidence-based report generator
4. Evaluation on the SmartBugs benchmark (Slither-only, LLM-only, hybrid)
