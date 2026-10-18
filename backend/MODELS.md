The local CPU backend uses **Depth Anything V2 Small**, an Apache-2.0 licensed
relative depth model by Lihe Yang and collaborators. It is downloaded at setup
time and is not committed to this repository.

- Original project: https://github.com/DepthAnything/Depth-Anything-V2
- ONNX conversion: https://github.com/fabio-sim/Depth-Anything-ONNX
- Pinned release: `v2.0.0`, asset `depth_anything_v2_vits.onnx`
- SHA-256: `d2b11a11c1d4a12b47608fa65a17ee9a4c605b55ee1730c8e3b526304f2562be`

The pinned checksum was recorded from the release asset downloaded over verified
HTTPS. Downloads and server startup verify it before using the file. No security
verification is disabled.

Predictions are relative inverse depth, not measured distances. A single image
does not contain hidden surfaces; the viewer can only build an approximate visible
surface. Photos are processed by the local backend and are not sent to a model
provider or saved to the checkout. Multipart parsing may use temporary files,
which are closed when the upload has been read.
