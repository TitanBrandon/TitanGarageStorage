Run these commands from the repository root with Python 3.12:

```sh
python3 -m venv /workspace/.titan-venv
/workspace/.titan-venv/bin/python -m pip install -r backend/requirements.txt
/workspace/.titan-venv/bin/python -m backend.download_model
/workspace/.titan-venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

The frontend forwards `/api` to this loopback backend. Keep it bound to loopback;
this prototype does not provide public API authentication or rate limiting across
users. The inference engine handles one photo at a time and rejects overlapping
requests rather than building an unbounded CPU queue.

`GET /api/health` returns `{ready, model, error}`. `POST /api/depth` accepts multipart
field `photo` (JPG, PNG or WebP; 15 MB maximum; at least 128 pixels in each
direction; at most 24 megapixels). Its JSON response includes `depth` (a grayscale
PNG data URI), `width`, `height`, `model`, `depthConvention: "near-is-white"`,
`inferenceMs`, and `metric: false`. Dimensions match the EXIF-corrected photo,
reduced to a maximum long edge of 1600 pixels. Depth is relative, not meters.

The model downloads from `github.com` and `release-assets.githubusercontent.com`;
Python wheels use the configured package index. No model service API key is
required. Runtime inference does not access the internet. Photo uploads may use
temporary files while multipart data is parsed; the files are closed after each
request, and the application does not keep an uploaded photo library.

To run the API checks (including real CPU inference):

```sh
/workspace/.titan-venv/bin/python -m unittest backend.test_api -v
```

The model's source, license and checksum are documented in [MODELS.md](MODELS.md).
