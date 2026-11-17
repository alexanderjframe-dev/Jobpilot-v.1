# JobPilot on iPhone

JobPilot is a Python/FastAPI web app. GitHub stores the code, but does **not** host the working app. GitHub Pages cannot run this Python backend.

## Deploy a private web app with Render

1. Open Render and connect your GitHub account.
2. Select **New → Blueprint** and the `alexanderjframe-dev/Jobpilot-v.1` repository (its `render.yaml` supplies the setup).
3. **Review pricing before creating the service.** The included `starter` service and persistent disk are paid resources. A free web service has an ephemeral filesystem and would lose your resume, preferences and application history after restart/redeploy; it is not recommended for this app.
4. Render will ask for `JOBPILOT_ACCESS_PASSWORD`. Create a strong unique password of at least 16 characters. Do not put the password into GitHub or chat.
5. Deploy, then open the HTTPS `.onrender.com` URL that Render actually assigns. Do not guess a URL. Enter username `jobpilot` and your password when Safari prompts.
6. In iPhone Safari, tap **Share → Add to Home Screen**. JobPilot can now be launched as a Home Screen web app. It still requires internet.

## What works on the phone

- Job discovery, preferences, profile and resume uploads, application queue, exports, and opening employer job links.
- On the hosted version, **Apply assist** opens an employer link for manual completion; it **does not** launch a browser on the server or submit an application. Mark `Applied` only after employer confirmation.
- Desktop Playwright auto-fill remains local-only.

## Security

Hosted mode requires Basic authentication on every private page/API call and rejects cross-site write requests. Use **HTTPS only** and a unique long password. This is a single-user MVP rather than multi-account auth. Keep backups of your data; Render disk snapshots are not a complete backup strategy. Your local computer data does not sync into the hosted database automatically.

## Manual hosting alternative

On a supported HTTPS host with a persistent filesystem and Python 3.10+:

- Set `JOBPILOT_HOSTED=1`, `JOBPILOT_ACCESS_PASSWORD` (16+ characters), and `JOBPILOT_DATA_DIR` to a durable directory.
- Install `requirements.txt` and start `uvicorn app:app --host 0.0.0.0 --port $PORT`.
- Ensure the host is configured for HTTPS and restrict access to this single-user instance.
