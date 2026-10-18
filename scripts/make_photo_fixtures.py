"""Reproduce permitted real-photo inputs. Requires worker Python dependencies.

Project captured Poly Haven HDR photographs into ordinary rectilinear photos.
The reconstruction itself receives just one JPEG, without panorama metadata.
"""
import argparse
import hashlib
from pathlib import Path
import urllib.request

import cv2
import numpy as np

ASSETS = [
    ('warehouse', 'empty_warehouse_01', 0, '9b3d611cadc32c3a0c7e084ce5611c0650293881c4a041e7fa13748fe0dc6451'),
    ('room', 'lebombo', 300, 'a02c9615adeba91a753c3e4737c3ce7a719273df822eeaa85d24982bd43c9ecb'),
]
REVISION = '456060a26bbeb8fdf79326f224b6d99b8bcce736'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('/tmp/titan-photo-originals'))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    output = Path(__file__).resolve().parents[1] / 'validation/photos'
    output.mkdir(parents=True, exist_ok=True)
    for name, asset, yaw, digest in ASSETS:
        original = args.cache / (asset + '_1k.hdr')
        if not original.is_file():
            url = f'https://raw.githubusercontent.com/pmndrs/drei-assets/{REVISION}/hdri/{asset}_1k.hdr'
            with urllib.request.urlopen(url, timeout=60) as response:
                original.write_bytes(response.read(8 * 1024 * 1024))
        if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Source photograph failed its pinned SHA-256 check.')
        hdr = cv2.imread(str(original), cv2.IMREAD_UNCHANGED)
        if hdr is None:
            raise RuntimeError('Could not decode the source photograph.')
        # Fixed Reinhard tone mapping followed by sRGB-like gamma; no generative edits.
        mapped = np.power(np.clip(hdr / (1 + hdr), 0, 1), 1 / 2.2)
        h, w = hdr.shape[:2]
        ww, hh = 640, 426
        focal = ww / 2 / np.tan(np.radians(90) / 2)
        xx, yy = np.meshgrid((np.arange(ww) - (ww-1)/2)/focal, -(np.arange(hh) - (hh-1)/2)/focal)
        pitch, angle = np.radians(-9), np.radians(yaw)
        x = xx
        y = yy*np.cos(pitch) + np.sin(pitch)
        z = -yy*np.sin(pitch) + np.cos(pitch)
        rx = x*np.cos(angle) + z*np.sin(angle)
        rz = -x*np.sin(angle) + z*np.cos(angle)
        longitude = np.arctan2(rx, rz)
        latitude = np.arctan2(y, np.sqrt(rx*rx + rz*rz))
        mx = ((longitude/(2*np.pi)+.5)*w).astype('float32')
        my = ((.5-latitude/np.pi)*h).astype('float32')
        photo = (cv2.remap(mapped, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)*255).astype('uint8')
        destination = output/(name + '.jpg')
        cv2.imwrite(str(destination), photo)
        print(name, hashlib.sha256(destination.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
