# craftcode — Web App Spec

## What It Is
Craftcode is now a browser-based repository review tool. A user pastes a GitHub URL, the backend clones and scans the repo, and a model returns a structured engineering review that covers:

- styling and frontend consistency issues
- test gaps and suggested tests
- clean code and maintainability problems
- design-pattern opportunities such as factory or strategy where they genuinely fit
- CI/CD, security, and dependency risks

## Current Architecture
```text
craftcode/
├── craftcode.py         # shared scan, prompt, analysis, and optional CLI entrypoint
├── server.py            # FastAPI app serving API + HTML
├── templates/
│   └── index.html       # dashboard shell
├── static/
│   ├── app.js           # client-side submission + report rendering
│   └── styles.css       # visual system
└── requirements.txt
```

## User Flow
1. User opens the web app.
2. User pastes a GitHub URL.
3. Frontend sends `POST /api/analyze`.
4. Backend clones the repo into a temp directory.
5. Source files are collected, filtered, and packed into an LLM prompt.
6. The model returns structured JSON.
7. The dashboard renders summary metrics, issue tables, and top priorities.
8. User can export the JSON report.

## API
### `GET /`
Serves the web app.

### `GET /health`
Returns:
```json
{ "status": "ok" }
```

### `POST /api/analyze`
Body:
```json
{ "target": "https://github.com/user/repo" }
```

Returns:
```json
{
  "summary": {
    "overall_grade": "A/B/C/D/F",
    "health_score": 0,
    "total_issues": 0,
    "critical_issues": 0
  },
  "missing_tests": [],
  "styling_issues": [],
  "design_pattern_issues": [],
  "clean_code_violations": [],
  "ci_cd_issues": [],
  "security_issues": [],
  "dependency_issues": [],
  "top_priorities": []
}
```

## Run
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Then open `http://localhost:8000`.

## Notes
- If `GEMINI_API_KEY` is present, Craftcode runs a model-backed review.
- Without the API key, the app falls back to scaffold guidance so the UI still works.
- The CLI path in `craftcode.py` still exists for local terminal use, but the main product is now the web app.
