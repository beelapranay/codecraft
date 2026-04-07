# craftcode — Frontend Notes

## Product Direction
The frontend is a lightweight dashboard served directly by FastAPI. There is no separate React build step in the current version, which keeps the app runnable from a single Python environment.

## Screen Structure
### Input panel
- GitHub URL field
- Analyze button
- status and error banners
- quick explanation of what the review checks

### Report dashboard
- summary cards for grade, score, total issues, and critical issues
- top priorities panel
- collapsible sections for:
  - tests to add
  - styling issues
  - design-pattern opportunities
  - clean code violations
  - CI/CD issues
  - security issues
  - dependency issues
- export JSON button
- reset button

## Rendering Approach
- `templates/index.html` provides the app shell.
- `static/app.js` posts to `/api/analyze` and renders the returned report.
- `static/styles.css` defines the visual system and responsive layout.

## Why This Shape
- one runtime instead of separate Python and Node processes
- easier local setup for a prototype
- faster path to validating the product flow before introducing a heavier frontend stack

## Future Upgrades
- swap the static frontend for React if the UI grows more stateful
- add streaming progress updates during clone and analysis
- support authenticated/private repository access
- add local folder upload with zip extraction
