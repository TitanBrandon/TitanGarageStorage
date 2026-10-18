# Open Space Studio from a website

Deploy this app once to Render, then open its web address from Windows, a phone,
or another computer. Your computer does not need Python, Node.js, or a terminal.
The website uses the World Labs API to generate scenes; its key stays on the
server. A shared password protects the app and its paid generation endpoints.

[**Deploy Space Studio to Render**](https://render.com/deploy?repo=https://github.com/TitanBrandon/TitanGarageStorage)

## First deployment

1. Open the deployment link and sign in to Render or create an account. If
   prompted, connect GitHub and allow access to `TitanBrandon/TitanGarageStorage`.
2. Render reads this repository's `render.yaml`. It creates one **Free** web
   service named `titan-space-studio`. Keep the Free plan for this experiment.
3. Enter your **World Labs API key** for `WORLDLABS_API_KEY` in Render's secure
   environment field. Get an API key and generation credits from
   [World Labs](https://platform.worldlabs.ai/). Do not put the key in a source
   file, a GitHub commit, or this chat.
4. Deploy the Blueprint and wait for the service to show **Live**. The first
   build installs dependencies and builds the app, so it can take several minutes.
5. Open the service in your Render dashboard. In **Environment**, reveal and
   copy the automatically generated `SITE_PASSWORD` into your password manager.
   If your dashboard does not let you reveal it, replace it there with a unique
   password of at least 16 characters and save/redeploy.
6. Click the service's `https://...onrender.com` address. When your browser asks
   for a username and password, use **`titan`** and your `SITE_PASSWORD`.
7. Bookmark that address. On later visits, open the bookmark, sign in if asked,
   upload a photo, and start a generation.

Creating or publishing a Codex development environment does not create this
Render website. The deployment link starts a separate hosting setup; this
repository does not provision a hosting account or spend provider credits.

## Costs and availability

The Blueprint requests Render's Free web service. Review Render's current limits
and pricing before deploying. Free services sleep when unused, so the first visit
after a break may take roughly a minute to wake up. Upgrading to a paid instance
is optional if you later want the service to stay awake.

World Labs generation still uses your World Labs credits. You approve a new
generation in the app; restarting the site or reopening an existing operation
does not automatically request another paid generation. Never share the site
password with someone you do not want using your generation credits.

The app has a shared login for this personal experiment. It does not provide
separate customer accounts, per-person usage budgets, or a permanent photo
library. Generated scenes remain subject to the provider's availability and
retention. A single photo also estimates unseen areas; it is not a measured scan.

## Updates and troubleshooting

Automatic deployment is disabled. After changes reach GitHub, open the Render
service and select **Manual Deploy → Deploy latest commit** when you want to
publish them. Changes to `render.yaml` itself may require syncing its Blueprint
in the Render dashboard.

- **Cannot sign in:** the username is exactly `titan`; reset `SITE_PASSWORD` in
  Render's Environment settings if necessary, then save/redeploy.
- **Provider is not connected:** confirm `WORLDLABS_API_KEY` is present in
  Render's Environment settings and that the account has API access and credits.
- **First visit waits:** allow the Free service to wake up, then reload once.
- **Deployment fails:** open Render's build/runtime logs. The app expects its
  compiled frontend in `dist/`, a `SITE_PASSWORD` of at least 16 characters, and a valid `PORT`.
  The included multi-stage Dockerfile creates the frontend and the small Python
  API runtime together. It does not install or download the old depth model.
- **A generation is already running:** return to the existing operation in the
  same browser; do not repeatedly submit the photo and incur extra charges.

The health check is `GET /healthz`; the app and its generation API require the
shared login. Environment secrets are runtime settings and are never build
arguments. Public hosting has not been verified until a Render deployment is
Live and a browser successfully signs in. A real World Labs generation also
requires an authorized key and sufficient credits.

Official references: [Render Blueprints](https://render.com/docs/infrastructure-as-code),
[Blueprint specification](https://render.com/docs/blueprint-spec), and
[Free services](https://render.com/docs/free).

## Development verification

The hosted server checks run with `python -m unittest backend.test_hosted backend.test_worlds -v`.
`python scripts/build_hosted.py` builds the image on a normal Docker host.
Inside the managed cloud workspace, use `python scripts/build_hosted.py --cloud-network`:
the helper preserves the existing proxy and certificate verification, maps the
proxy hostname for the Docker builder, and uses a temporary public CA secret.
Proxy values and the trust bundle are not copied into the final image. Render's
normal build does not need these managed-cloud options.
