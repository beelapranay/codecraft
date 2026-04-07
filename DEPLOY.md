# Deploy Craftcode

Craftcode is ready to deploy as a single Dockerized FastAPI app.

## Required Environment Variables
- `GEMINI_API_KEY`
- `CRAFTCODE_MODEL` optional, default is `gemini-2.5-flash`

## Local Docker Test
Build:
```bash
docker build -t craftcode .
```

Run:
```bash
docker run -p 8000:8000 --env GEMINI_API_KEY=your_key_here craftcode
```

Then open `http://localhost:8000`.

## Render
1. Push this project to GitHub.
2. In Render, create a new `Web Service`.
3. Connect the repo.
4. Choose `Docker` as the runtime.
5. Add environment variable `GEMINI_API_KEY`.
6. Deploy.

Render will provide the `PORT` variable automatically. The Dockerfile already honors it.

## Railway
1. Push this project to GitHub.
2. In Railway, create a new project from the repo.
3. Railway will detect the `Dockerfile`.
4. Add environment variable `GEMINI_API_KEY`.
5. Deploy.

Railway also injects `PORT`, which the Dockerfile uses automatically.

## Notes
- Do not commit your real `.env` with a live Gemini key.
- The current report page stores the latest report in browser session storage, not a database.
- If you want persistent reports or team logins, add a datastore before production use.
