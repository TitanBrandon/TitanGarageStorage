# Real-photo validation inputs and permission

These are perspective crops of real HDR photographs, not rendered room fixtures
or prebuilt models. They provide two different interiors for running the entire
uploaded-image → analysis → Blender → browser pipeline. They are not the user's
private garage photo, which was unavailable as a local file in this task.

| File | Source asset | Crop | Dimensions |
| --- | --- | --- | --- |
| `warehouse.jpg` | Poly Haven / HDRI Haven, [Empty Warehouse 01](https://polyhaven.com/a/empty_warehouse_01) | yaw 0°, pitch −9°, horizontal field of view 90° | 640 × 426 |
| `room.jpg` | Poly Haven / HDRI Haven, [Lebombo](https://polyhaven.com/a/lebombo) | yaw 300°, pitch −9°, horizontal field of view 90° | 640 × 426 |

The originals are 1024 × 512 equirectangular Radiance HDR photographs. The test
pipeline receives only the derived, ordinary perspective JPEG, not the full
panorama or any additional camera views. Thus each reconstruction still uses a
single image. The 90° perspective crop resamples approximately one quarter of a
low-resolution panorama and is useful for integration and coarse geometry tests;
it provides limited fine texture, cabinet-edge, and dimensional evidence. These
fixtures do not establish fidelity on high-resolution garage photos, unseen
surfaces, or all supported object classes.

## Source and licensing evidence

Retrieved 2026-10-18 through the `pmndrs/drei-assets` mirror:

- [Original warehouse HDR](https://raw.githubusercontent.com/pmndrs/drei-assets/master/hdri/empty_warehouse_01_1k.hdr)
- [Original room HDR](https://raw.githubusercontent.com/pmndrs/drei-assets/master/hdri/lebombo_1k.hdr)
- [Mirror attribution README](https://github.com/pmndrs/drei-assets/blob/456060a26bbeb8fdf79326f224b6d99b8bcce736/README.md) explicitly states “HDRIs from HDRI Haven.”

Poly Haven's [asset license](https://polyhaven.com/license) is
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/). The
canonical website and asset endpoints returned proxy HTTP 403 in this cloud
session, so licensing was independently verified in Poly Haven's official
website source at commit `b1a6aa13afc03ae00860f6ac5fe6d5daf8e95356`:

- [Official English asset-license content](https://github.com/Poly-Haven/polyhaven.com/blob/b1a6aa13afc03ae00860f6ac5fe6d5daf8e95356/public/locales/en/license.json) states “Our assets are all licensed as CC0” and explicitly permits redistribution, commercial use, and use without attribution.
- [Official license-page implementation](https://github.com/Poly-Haven/polyhaven.com/blob/b1a6aa13afc03ae00860f6ac5fe6d5daf8e95356/pages/license.tsx) renders that content at `/license` and links to the CC0 1.0 legal instrument.

Those are the asset license statements, separate from the license covering
Poly Haven's website source code. Credit is recorded here voluntarily even
though CC0 does not require attribution. No paid assets or private photos are
included in these fixtures.

## SHA-256 integrity

| File | SHA-256 |
| --- | --- |
| `empty_warehouse_01_1k.hdr` | `9b3d611cadc32c3a0c7e084ce5611c0650293881c4a041e7fa13748fe0dc6451` |
| `lebombo_1k.hdr` | `a02c9615adeba91a753c3e4737c3ce7a719273df822eeaa85d24982bd43c9ecb` |
| `warehouse.jpg` | `9ecce63f013e959fc85afe671d0e48f1fc7d8b1ab4dcb95ffc75cf126248f072` |
| `room.jpg` | `52f5c435984399ca053b6c50e57ee9b39b4634db6ecab7f8a57b5710c086bfd9` |

The fixture-generation script records the projection and tone-mapping method.
Original HDRs are downloaded during fixture generation rather than checked into
the application or used as browser environments. The reconstruction results and
walkthrough screenshots are recorded separately from these original inputs.
