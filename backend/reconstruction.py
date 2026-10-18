"""Deterministic CPU photo analysis for bounded, Manhattan-style interiors.

This is deliberately a conservative geometric reconstruction, not a generative
world model. Relative depth, line evidence and planar fits drive the layout;
unobservable metric scale is explicitly estimated. Unsupported images fail.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

from backend.model import MODEL_PATH, MODEL_SHA256
from backend.scene_schema import validate_scene

Progress = Callable[[str], None]


class ReconstructionError(ValueError):
    """The photo does not support a safe, useful reconstruction."""


def _report(progress, cancelled, message):
    if cancelled and cancelled():
        raise ReconstructionError("Reconstruction cancelled.")
    if progress:
        progress(message)


def _depth(rgb: np.ndarray) -> np.ndarray:
    path = Path(os.environ.get("TITAN_DEPTH_MODEL_PATH", str(MODEL_PATH)))
    if not path.is_file():
        raise ReconstructionError("The pinned local depth model is missing. Run python -m backend.download_model on the worker.")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != MODEL_SHA256:
            raise ReconstructionError("Depth model checksum verification failed; the model was not used.")
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
    pixels = cv2.resize(rgb, (518, 518), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    pixels = (pixels - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
    data = np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])
    result = np.squeeze(session.run(None, {session.get_inputs()[0].name: data})[0])
    if result.ndim != 2 or not np.isfinite(result).all():
        raise ReconstructionError("The local depth model returned an invalid prediction.")
    lo, hi = np.percentile(result, [1, 99])
    if hi - lo < 1e-5:
        raise ReconstructionError("The photo has too little depth variation. Include the floor, two wall boundaries and the ceiling.")
    return cv2.resize(((result-lo)/(hi-lo)).clip(0, 1).astype(np.float32), (rgb.shape[1], rgb.shape[0]))


def _plane(depth, region, *, axis=None, seed=19):
    """RANSAC affine inverse-depth plane, with robust least-squares refinement."""
    h, w = depth.shape
    yy, xx = np.nonzero(region)
    if len(xx) < 120:
        return None
    rng = np.random.default_rng(seed)
    chosen = rng.choice(len(xx), min(5000, len(xx)), replace=False)
    xx, yy = xx[chosen], yy[chosen]
    a = np.column_stack((xx/w, yy/h, np.ones(len(xx))))
    b = depth[yy, xx]
    best = None
    best_score = -1
    for _ in range(220):
        ix = rng.choice(len(xx), 3, replace=False)
        try:
            coefficients = np.linalg.solve(a[ix], b[ix])
        except np.linalg.LinAlgError:
            continue
        if axis == "floor" and not (.18 < coefficients[1] < 3.5 and abs(coefficients[0]) < .75):
            continue
        residual = np.abs(a @ coefficients - b)
        inliers = residual < .045
        score = inliers.sum()
        if score > best_score:
            best, best_score = inliers, score
    if best is None or best_score < 70:
        return None
    coefficients = np.linalg.lstsq(a[best], b[best], rcond=None)[0]
    for _ in range(3):
        residual = np.abs(a @ coefficients - b)
        weights = 1 / np.maximum(.015, residual)
        coefficients = np.linalg.lstsq(a*weights[:, None], b*weights, rcond=None)[0]
    gy, gx = np.mgrid[:h, :w]
    prediction = coefficients[0]*gx/w + coefficients[1]*gy/h + coefficients[2]
    mask = (np.abs(prediction-depth) < .055).astype(np.uint8)
    return coefficients, prediction, mask, float(best_score/len(xx))


def _lines(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    found = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    if found is None:
        return np.empty((0, 4), np.float32)
    lines = found[:, 0]
    lengths = np.linalg.norm(lines[:, 2:]-lines[:, :2], axis=1)
    return lines[lengths > min(rgb.shape[:2])*.065]


def _vanishing_point(lines, w, h):
    """Find the forward Manhattan vanishing point from converging room edges."""
    candidates = []
    selected = []
    for line in lines:
        x1, y1, x2, y2 = line
        dx, dy = float(x2-x1), float(y2-y1)
        slope = abs(dy/(dx or 1e-6))
        if .10 < slope < 2.8 and abs(dx) > .06*w:
            selected.append(line)
    selected = sorted(selected, key=lambda l: float(np.linalg.norm(l[2:]-l[:2])), reverse=True)[:75]
    for i, a in enumerate(selected):
        la = np.cross([a[0], a[1], 1], [a[2], a[3], 1])
        for b in selected[i+1:]:
            # Opposite slopes anchor the vanishing point; parallel texture lines do not.
            if (a[3]-a[1])*(b[3]-b[1])*(a[2]-a[0])*(b[2]-b[0]) >= 0:
                continue
            lb = np.cross([b[0], b[1], 1], [b[2], b[3], 1])
            v = np.cross(la, lb)
            if abs(v[2]) < 1e-6:
                continue
            x, y = v[:2]/v[2]
            if .12*w < x < .88*w and .16*h < y < .73*h:
                candidates.append((x, y))
    if not candidates:
        return (w*.5, h*.42), 0
    candidates = np.array(candidates)
    # Densest cluster rather than mean of unrelated wall/cabinet intersections.
    votes = np.array([np.sum(np.linalg.norm((candidates-v)/[w, h], axis=1) < .055) for v in candidates])
    peak = candidates[int(votes.argmax())]
    cluster = candidates[np.linalg.norm((candidates-peak)/[w, h], axis=1) < .08]
    return tuple(np.median(cluster, axis=0)), int(votes.max())


def _layout(rgb, depth, lines):
    h, w = depth.shape
    yy, xx = np.mgrid[:h, :w]
    lower = (yy > .64*h) & (xx > .12*w) & (xx < .88*w)
    fit = _plane(depth, lower, axis="floor")
    if fit is None:
        raise ReconstructionError("A reliable floor plane could not be found. Use a room photo with a broad visible floor, wall corners and an uncluttered lower centre.")
    coeff, floor_prediction, mask, support = fit
    vp, votes = _vanishing_point(lines, w, h)
    # The fitted floor's lower extent must connect with the camera-facing edge.
    mask[yy < .36*h] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    label = 0
    best = 0
    for i in range(1, n):
        bottom = int(np.sum(labels[int(.88*h):, :] == i))
        score = bottom + stats[i, cv2.CC_STAT_AREA]*.05
        if bottom > w*2 and score > best:
            label, best = i, score
    floor_mask = (labels == label).astype(np.uint8) if label else np.zeros_like(mask)
    coverage = float(floor_mask.mean())
    if coverage < .095 or support < .25:
        raise ReconstructionError("The floor is too occluded or non-planar for automatic room reconstruction. Include more floor and the floor/wall junction, or use another photograph.")
    starts = []
    for x in range(int(.25*w), int(.75*w), max(1, w//80)):
        col = cv2.blur(floor_mask[:, x:x+1].astype(np.float32), (1, 15))[:, 0]
        hits = np.where((col > .7) & (np.arange(h) > max(vp[1]+.06*h, .4*h)))[0]
        if len(hits):
            starts.append(hits[0])
    floor_y = float(np.percentile(starts, 30)) if starts else .62*h
    horizontal = []
    vertical = []
    for line in lines:
        x1, y1, x2, y2 = map(float, line)
        length = math.hypot(x2-x1, y2-y1)
        if abs(y2-y1) < abs(x2-x1)*.12 and length > .12*w:
            horizontal.append((float((y1+y2)/2), min(x1,x2), max(x1,x2), length))
        if abs(x2-x1) < abs(y2-y1)*.13 and length > .18*h:
            vertical.append((float((x1+x2)/2), min(y1,y2), max(y1,y2), length))
    base_candidates = [l for l in horizontal if max(.40*h, vp[1]+.045*h) < l[0] < .85*h]
    if base_candidates:
        base = min(base_candidates, key=lambda l: abs(l[0]-floor_y)/h - .09*l[3]/w)
        if abs(base[0]-floor_y) < .17*h:
            floor_y = base[0]
    floor_y = float(np.clip(floor_y, max(.45*h, vp[1]+.08*h), .83*h))
    lefts = [l for l in vertical if .06*w < l[0] < .46*w and l[1] < floor_y-.14*h and l[2] > floor_y-.14*h]
    rights = [l for l in vertical if .54*w < l[0] < .94*w and l[1] < floor_y-.14*h and l[2] > floor_y-.14*h]
    # Prefer room-sized long boundaries rather than a particular cabinet door seam.
    xl = min(lefts, key=lambda l: l[0]/w-.3*l[3]/h)[0] if lefts else 0.
    xr = max(rights, key=lambda l: l[0]/w+.3*l[3]/h)[0] if rights else float(w-1)
    tops = [l for l in horizontal if .01*h < l[0] < min(vp[1]-.08*h, floor_y-.25*h) and l[3] > .55*(xr-xl)]
    # A door header is not the wall/ceiling junction. A cropped ceiling remains
    # outside the photograph instead of becoming a low roof through the door.
    ceiling_visible = bool(tops)
    ceiling_y = max(tops, key=lambda l: l[3])[0] if tops else 0.
    ceiling_y = min(ceiling_y, floor_y-.27*h)
    if (xr-xl) < .35*w or floor_y-ceiling_y < .25*h:
        raise ReconstructionError("The room boundaries are ambiguous. Use a wider interior view that includes the wall/floor and wall/ceiling junctions.")
    # A room is supported by depth plus edge evidence. A blank outdoor plane must not become a garage.
    edge_count = len(vertical) + len(horizontal)
    if edge_count < 4 or (not lefts and not rights and votes < 2):
        raise ReconstructionError("No supported interior wall layout was found. Try a photo showing clear vertical wall corners and a ceiling; outdoor/open-sided scenes are currently unsupported.")
    return {"corners": [xl, xr, ceiling_y, floor_y], "vp": vp, "votes": votes,
            "floor_mask": floor_mask, "floor_prediction": floor_prediction, "floor_plane": coeff,
            "floor_coverage": coverage, "floor_support": support,
            "corner_sides": int(bool(lefts))+int(bool(rights)), "edge_count": edge_count,
            "ceiling_visible": ceiling_visible}


def _camera(layout, w, h):
    xl, xr, yt, yb = layout["corners"]
    vx, vy = layout["vp"]
    # Horizontal FoV prior; scale is an explicit 2.7 m room-height prior.
    f = w / (2*math.tan(math.radians(67)/2))
    pitch = math.atan((vy-h/2)/f)
    cp, sp = math.cos(pitch), math.sin(pitch)
    def ray(x, y):
        q = np.array([(x-w/2)/f, -(y-h/2)/f, -1.])
        return np.array([q[0], cp*q[1]-sp*q[2], sp*q[1]+cp*q[2]])
    top, bottom = ray((xl+xr)/2, yt), ray((xl+xr)/2, yb)
    top_y, bottom_y = top[1]/-top[2], bottom[1]/-bottom[2]
    height = 2.7
    distance = height / max(.15, top_y-bottom_y)
    eye = float(np.clip(-bottom_y*distance, 1.05, 2.1))
    # Recompute from the fitted floor (eye height) rather than invent metric depth.
    distance = eye/max(.08, -bottom_y)
    width = float(np.clip((ray(xr,yb)[0]/-ray(xr,yb)[2]-ray(xl,yb)[0]/-ray(xl,yb)[2])*distance, 2.2, 18))
    distance = float(np.clip(distance, 2.2, 18))
    height = float(np.clip((top_y-bottom_y)*distance, 2.2, 5.5))
    depth = distance + .65
    cam_x = -((xl+xr)/2-w/2)/f*distance
    cam_x = float(np.clip(cam_x, -width*.35, width*.35))
    cam_z = depth/2-.65
    position = np.array([cam_x, eye, cam_z])
    forward = np.array([0, sp, -cp])
    # Correct visible asymmetry by horizontal principal-ray shift; report yaw limitations.
    return {"width": width, "height": height, "depth": depth, "position":position,
            "target":position+forward*distance, "f": f, "pitch":pitch,
            "fov":math.degrees(2*math.atan(h/(2*f))), "ray":ray}


def _project(points, camera, w, h):
    points = np.asarray(points, np.float64)-camera["position"]
    cp, sp = math.cos(camera["pitch"]), math.sin(camera["pitch"])
    x = points[:,0]
    y = cp*points[:,1]+sp*points[:,2]
    z = -sp*points[:,1]+cp*points[:,2]
    near = np.maximum(.1, -z)
    return np.column_stack((w/2+camera["f"]*x/near, h/2-camera["f"]*y/near)).astype(np.float32)


def _intersect(x, y, camera, *, wall="back", offset=0.):
    ray = camera["ray"](x, y)
    pos = camera["position"]
    if wall == "back":
        t = (-camera["depth"]/2+offset-pos[2])/ray[2]
    elif wall == "left":
        t = (-camera["width"]/2+offset-pos[0])/ray[0]
    elif wall == "right":
        t = (camera["width"]/2-offset-pos[0])/ray[0]
    else:
        t = -pos[1]/ray[1]
    return pos + ray*max(.1,float(t))


def _color(rgb, mask, fallback=None):
    pixels = rgb[mask.astype(bool)]
    if len(pixels) < 30:
        if fallback is None:
            return [.65,.65,.65]
        pixels = rgb[fallback]
    if len(pixels) == 0:
        return [.65,.65,.65]
    return (np.median(pixels, axis=0)/255).round(4).tolist()


def _patch(rgb, mask, out, name, *, rect=None):
    """Select a source-only material patch; no room photograph is wrapped onto a box."""
    h,w = mask.shape
    if rect is not None:
        quad = np.asarray(rect,np.float32)
        dw = int(min(1024, max(96, np.linalg.norm(quad[1]-quad[0]))))
        dh = int(min(1024, max(96, np.linalg.norm(quad[3]-quad[0]))))
        matrix = cv2.getPerspectiveTransform(quad, np.float32([[0,0],[dw-1,0],[dw-1,dh-1],[0,dh-1]]))
        patch = cv2.warpPerspective(rgb,matrix,(dw,dh),borderMode=cv2.BORDER_REFLECT_101)
    else:
        best, location = 0, None
        size = max(20,min(h,w)//9)
        integral = cv2.integral(mask.astype(np.uint8))
        for y in range(0,h-size,max(4,size//3)):
            for x in range(0,w-size,max(4,size//3)):
                score = integral[y+size,x+size]-integral[y,x+size]-integral[y+size,x]+integral[y,x]
                if score > best:
                    best,location = score,(x,y)
        if location is None or best < size*size*.88:
            return None
        x,y=location
        patch=rgb[y:y+size,x:x+size]
        patch=cv2.resize(patch,(256,256),interpolation=cv2.INTER_CUBIC)
        # Reduce low-frequency exposure gradients; preserve finish detail at source scale.
        low=cv2.GaussianBlur(patch.astype(np.float32),(0,0),24)
        patch=np.clip(patch.astype(np.float32)-low+np.median(patch,axis=(0,1)),0,255).astype(np.uint8)
    path=out/"textures"/f"{name}.png"
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(patch).save(path)
    return f"textures/{name}.png"


def _seamless_floor(path, tile_size, out):
    """Remove illumination from the source finish, then mirror-periodize it.

    The two-by-two mirror repeats continuously at every edge. Doubling the
    physical tile size preserves the measured source grain scale.
    """
    if not path:
        return path,tile_size
    destination=out/path
    pixels=np.asarray(Image.open(destination).convert("RGB"),dtype=np.float32)
    sigma=max(8.,min(pixels.shape[:2])*.12)
    illumination=cv2.GaussianBlur(pixels,(0,0),sigma)
    finish=np.clip(pixels-illumination+np.median(pixels,axis=(0,1)),0,255).astype(np.uint8)
    row=np.concatenate([finish,finish[:,::-1]],axis=1)
    periodic=np.concatenate([row,row[::-1]],axis=0)
    Image.fromarray(periodic).save(destination)
    return path,tile_size*2


def _floor_patch(rgb, mask, camera, out):
    """Rectify a clean floor patch through the solved ground-plane homography."""
    h,w=mask.shape
    for py in (.88,.80,.73):
        for px in (.5,.35,.65):
            if not mask[int(h*py),int(w*px)]:
                continue
            center=_intersect(w*px,h*py,camera,wall="floor")
            for side in (.8,.5,.3):
                half=side/2
                quad=_project([[center[0]-half,0,center[2]-half],[center[0]+half,0,center[2]-half],
                               [center[0]+half,0,center[2]+half],[center[0]-half,0,center[2]+half]],camera,w,h)
                if np.min(quad)<2 or quad[:,0].max()>w-3 or quad[:,1].max()>h-3:
                    continue
                test=np.zeros(mask.shape,np.uint8);cv2.fillConvexPoly(test,quad.astype(np.int32),1)
                if np.mean(mask[test.astype(bool)])<.94:
                    continue
                path=_patch(rgb,mask,out,"floor",rect=quad)
                return _seamless_floor(path,side,out)
    return _seamless_floor(_patch(rgb,mask,out,"floor"),.8,out)


def _surface_texture(rgb, camera, out, name, points, color):
    """Perspective-rectified source surface, with unseen pixels filled by finish.

    Each map belongs to one independently reconstructed plane; objects are
    removed from its pixels by callers and remain separate meshes.
    """
    h,w=rgb.shape[:2]
    quad=_project(points,camera,w,h)
    tw=max(128,min(1024,int(math.dist(points[0],points[1])*150)))
    th=max(128,min(1024,int(math.dist(points[0],points[3])*150)))
    homography=cv2.getPerspectiveTransform(quad,np.float32([[0,0],[tw-1,0],[tw-1,th-1],[0,th-1]]))
    patch=cv2.warpPerspective(rgb,homography,(tw,th),flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT,borderValue=tuple(int(c*255) for c in color))
    path=out/"textures"/f"{name}.png";path.parent.mkdir(exist_ok=True,parents=True)
    Image.fromarray(patch).save(path)
    return f"textures/{name}.png"


def _wall_mask(shape, layout, wall):
    h,w=shape
    xl,xr,yt,yb=layout["corners"]
    vx,vy=layout["vp"]
    if wall=="back":
        poly=[[xl,yt],[xr,yt],[xr,yb],[xl,yb]]
    elif wall=="left":
        if xl<.045*w:
            return np.zeros(shape,np.uint8)
        factor=(0-vx)/(xl-vx) if abs(xl-vx)>1 else 1
        poly=[[0,vy+(yt-vy)*factor],[xl,yt],[xl,yb],[0,vy+(yb-vy)*factor]]
    else:
        if xr>.955*w:
            return np.zeros(shape,np.uint8)
        factor=(w-1-vx)/(xr-vx) if abs(xr-vx)>1 else 1
        poly=[[xr,yt],[w-1,vy+(yt-vy)*factor],[w-1,vy+(yb-vy)*factor],[xr,yb]]
    mask=np.zeros(shape,np.uint8)
    cv2.fillConvexPoly(mask,np.asarray(poly,np.int32),1)
    return mask


def _regions(rgb, depth, layout, camera, lines, wall_name="back"):
    """Conservative foreground rectangles anchored by the wall depth plane."""
    h,w=depth.shape
    xl,xr,yt,yb=layout["corners"]
    yy,xx=np.mgrid[:h,:w]
    back=_wall_mask(depth.shape,layout,wall_name).astype(bool)
    if wall_name=="left":
        region_xl,region_xr=0,xl
    elif wall_name=="right":
        region_xl,region_xr=xr,w-1
    else:
        region_xl,region_xr=xl,xr
    if np.sum(back)<.035*w*h:
        return [],[],back.astype(np.uint8)
    fit=_plane(depth,back,seed=31)
    if fit is None:
        return [],[],back.astype(np.uint8)
    _,prediction,_,_ = fit
    object_region=back.copy()
    if wall_name=="back":
        object_region=(xx>xl+3)&(xx<xr-3)&(yy>yt+3)&(yy<min(h,yb+.18*h))
    # Relative-depth values have no universal metre threshold. A modest signed
    # residual plus a compact rectangular silhouette supports a foreground box.
    foreground=((depth-prediction)>.035)&object_region&(~layout["floor_mask"].astype(bool))
    foreground=cv2.morphologyEx(foreground.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((13,13),np.uint8))
    contours,_=cv2.findContours(foreground,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if bw<.055*w or bh<.09*h or bw*bh<.008*w*h or bw>.85*w or bh>.88*h:
            continue
        # A region cut by the photograph boundary is more often the room wall
        # or ceiling itself. Without a closed silhouette it is not an object.
        if x<.018*w or y<.018*h or x+bw>.982*w or y+bh>.982*h:
            continue
        fill=cv2.contourArea(contour)/max(1,bw*bh)
        if fill < .45:
            continue
        boxes.append((x,y,x+bw,y+bh,float(fill),"box"))
    # Explicit rectangular cabinet fronts: strong vertical edges, a bottom close
    # to the floor junction, and different depth from neighbouring wall pixels.
    vertical=[]
    horizontal=[]
    for line in lines:
        x1,y1,x2,y2=map(float,line)
        if abs(x2-x1)<.1*abs(y2-y1) and abs(y2-y1)>.16*h:
            vertical.append((float((x1+x2)/2),min(y1,y2),max(y1,y2)))
        if abs(y2-y1)<.1*abs(x2-x1) and abs(x2-x1)>.12*w:
            horizontal.append((min(x1,x2),max(x1,x2),float((y1+y2)/2)))
    for a in vertical:
        for b in vertical:
            x1,x2=sorted([a[0],b[0]])
            top=max(a[1],b[1]);bottom=min(a[2],b[2])
            if not(.08*w<x2-x1<.65*w and .18*h<bottom-top<.75*h and region_xl<x1<x2<region_xr):
                continue
            cap=[q for q in horizontal if q[0]<x1+.05*w and q[1]>x2-.05*w and abs(q[2]-top)<.04*h]
            if not cap or bottom < yb-.14*h:
                continue
            region=depth[int(top):int(bottom),int(x1):int(x2)]-prediction[int(top):int(bottom),int(x1):int(x2)]
            if region.size and np.median(region)>.035:
                boxes.append((int(x1),int(top),int(x2),int(bottom),.7,"cabinet"))
    boxes.sort(key=lambda q:(q[2]-q[0])*(q[3]-q[1]),reverse=True)
    kept=[]
    for box in boxes:
        x1,y1,x2,y2,confidence,kind=box
        overlap=False
        for old in kept:
            area=max(0,min(x2,old[2])-max(x1,old[0]))*max(0,min(y2,old[3])-max(y1,old[1]))
            if area / min((x2-x1)*(y2-y1),(old[2]-old[0])*(old[3]-old[1]))>.45:
                overlap=True;break
        if not overlap:
            kept.append(box)
    objects=[];masks=[]
    clean=back.copy()
    for i,(x1,y1,x2,y2,confidence,kind) in enumerate(kept[:16]):
        wall=wall_name
        p1=_intersect(x1,y1,camera,wall=wall);p2=_intersect(x2,y2,camera,wall=wall)
        width=abs(p2[0]-p1[0]) if wall=="back" else abs(p2[2]-p1[2])
        height=abs(p2[1]-p1[1])
        wall_length=camera["width"] if wall=="back" else camera["depth"]
        if width<.18 or height<.25 or width>wall_length*.9:
            continue
        bottom=max(0,float(min(p1[1],p2[1])))
        if bottom<.4:
            bottom=0.
        height=min(height,camera["height"]-bottom)
        if height<.2:
            continue
        if kind=="cabinet" and width>2.6:
            kind="box";confidence=min(confidence,.55)
        if kind=="box":
            confidence=min(confidence,.58)
        extent=float(np.clip(width*.3,.28,.7))
        # Size the front at its actual plane; moving a back-wall crop forward
        # without this correction would enlarge it in the source-camera view.
        p1=_intersect(x1,y1,camera,wall=wall,offset=extent+.015)
        p2=_intersect(x2,y2,camera,wall=wall,offset=extent+.015)
        width=abs(p2[0]-p1[0]) if wall=="back" else abs(p2[2]-p1[2])
        bottom=max(0.,float(min(p1[1],p2[1])))
        if bottom<.4:
            bottom=0.
        height=min(camera["height"]-bottom,max(.2,float(max(p1[1],p2[1]))-bottom))
        if wall=="back":
            pos=[float((p1[0]+p2[0])/2),bottom+height/2,-camera["depth"]/2+extent/2+.015];rotation=0.
        elif wall=="left":
            pos=[-camera["width"]/2+extent/2+.015,bottom+height/2,float((p1[2]+p2[2])/2)];rotation=math.pi/2
        else:
            pos=[camera["width"]/2-extent/2-.015,bottom+height/2,float((p1[2]+p2[2])/2)];rotation=-math.pi/2
        mask=np.zeros((h,w),np.uint8);mask[y1:y2,x1:x2]=1
        clean[y1:y2,x1:x2]=False
        object_id=f"{wall}-object-{i+1}"
        obj={"id":object_id,"kind":kind,"position":pos,"dimensions":[float(width),float(height),extent],
             "rotation_y":rotation,"wall_id":wall,"material":object_id,"confidence":round(confidence,3)}
        objects.append(obj);masks.append((mask,(x1,y1,x2,y2)))
    # Dense regular horizontal line bands support slat-wall panels, not furniture.
    bands=[]
    for x1,x2,y in horizontal:
        if yt+.05*h<y<yb-.08*h and x2-x1>.16*w:
            bands.append((x1,x2,y))
    if len(bands)>=7:
        bands.sort(key=lambda a:a[2])
        ys=np.array([b[2] for b in bands]);spacing=np.diff(ys)
        spacing=spacing[(spacing>2)&(spacing<.055*h)]
        if len(spacing)>=6 and np.std(spacing)/max(1,np.mean(spacing))<.5:
            x1=int(np.percentile([b[0] for b in bands],35));x2=int(np.percentile([b[1] for b in bands],65))
            y1=int(ys.min());y2=int(ys.max())
            if x1>region_xl and x2<region_xr and y2-y1>.12*h and not any(np.mean(m[0][y1:y2,x1:x2])>.3 for m in masks):
                p1=_intersect(x1,y1,camera,wall=wall_name);p2=_intersect(x2,y2,camera,wall=wall_name)
                mask=np.zeros((h,w),np.uint8);mask[y1:y2,x1:x2]=1
                center_y=float((p1[1]+p2[1])/2)
                if wall_name=="back":
                    position=[float((p1[0]+p2[0])/2),center_y,-camera["depth"]/2+.035];rotation=0.
                    panel_width=abs(p2[0]-p1[0])
                elif wall_name=="left":
                    position=[-camera["width"]/2+.035,center_y,float((p1[2]+p2[2])/2)];rotation=math.pi/2
                    panel_width=abs(p2[2]-p1[2])
                else:
                    position=[camera["width"]/2-.035,center_y,float((p1[2]+p2[2])/2)];rotation=-math.pi/2
                    panel_width=abs(p2[2]-p1[2])
                object_id=f"{wall_name}-slat-wall-1"
                obj={"id":object_id,"kind":"slat_wall","position":position,
                     "dimensions":[float(panel_width),float(abs(p2[1]-p1[1])),.06],"rotation_y":rotation,"wall_id":wall_name,"material":object_id,"confidence":.52}
                if min(obj["dimensions"][:2])>.2:
                    objects.append(obj);masks.append((mask,(x1,y1,x2,y2)));clean[y1:y2,x1:x2]=False
    return objects,masks,clean.astype(np.uint8)


def _openings(rgb, depth, layout, camera, wall_clean):
    """Only mark a bounded rectangular, deeper wall region as a possible opening."""
    h,w=depth.shape
    fit=_plane(depth,wall_clean,seed=74)
    if fit is None:
        return []
    _,prediction,_,_=fit
    far=((prediction-depth)>.14)&wall_clean.astype(bool)
    far=cv2.morphologyEx(far.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    contours,_=cv2.findContours(far,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    result=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        perimeter=cv2.arcLength(contour,True)
        approx=cv2.approxPolyDP(contour,.035*perimeter,True)
        if len(approx)!=4 or bw<.10*w or bh<.15*h or bw*bh>.35*w*h or cv2.contourArea(contour)<bw*bh*.75:
            continue
        p1=_intersect(x,y,camera);p2=_intersect(x+bw,y+bh,camera)
        left=max(-camera["width"]/2,float(min(p1[0],p2[0])))
        width=min(camera["width"]/2-left,abs(float(p2[0]-p1[0])))
        bottom=max(0,float(min(p1[1],p2[1])))
        if bottom<.4:
            bottom=0.
        height=min(camera["height"]-bottom,abs(float(p2[1]-p1[1])))
        if width>.4 and height>.5:
            result.append({"kind":"door" if bottom<.25 else "window","offset":left+camera["width"]/2,
                           "width":width,"height":height,"bottom":bottom,"confidence":.48,
                           "_source_bbox":[x,y,x+bw,y+bh]})
    # Bright rectangular apertures remain windows even when relative depth
    # saturates on outdoor light and cannot measure the space beyond the glass.
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    wall_pixels=gray[wall_clean.astype(bool)]
    if len(wall_pixels):
        threshold=max(205,float(np.median(wall_pixels))+50)
        bright=((gray>threshold)&wall_clean.astype(bool)&(np.indices(gray.shape)[0]<layout["corners"][3]-.10*h)).astype(np.uint8)
        bright=cv2.morphologyEx(bright,cv2.MORPH_CLOSE,np.ones((7,13),np.uint8))
        contours,_=cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,bw,bh=cv2.boundingRect(contour)
            if bw<.10*w or bh<.045*h or bw*bh>.20*w*h or cv2.contourArea(contour)<bw*bh*.58:
                continue
            p1=_intersect(x,y,camera);p2=_intersect(x+bw,y+bh,camera)
            left=max(-camera["width"]/2,float(min(p1[0],p2[0])))
            bottom=max(.35,float(min(p1[1],p2[1])))
            ow=min(camera["width"]/2-left,abs(float(p2[0]-p1[0])))
            oh=min(camera["height"]-bottom,abs(float(p2[1]-p1[1])))
            if ow>.35 and oh>.15 and bottom+oh<camera["height"]+.02:
                result.append({"kind":"window","offset":left+camera["width"]/2,"width":ow,"height":oh,"bottom":bottom,"confidence":.52,
                               "_source_bbox":[x,y,x+bw,y+bh]})
    return result[:4]


def analyze_photo(source_path: Path, output_dir: Path, progress: Progress | None = None,
                  cancelled: Callable[[], bool] | None = None) -> dict:
    source_path,output_dir=Path(source_path),Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    _report(progress,cancelled,"Analyzing perspective and estimating local CPU depth")
    with Image.open(source_path) as image:
        if image.width*image.height>24_000_000:
            raise ReconstructionError("Choose an image smaller than 24 megapixels.")
        image=ImageOps.exif_transpose(image).convert("RGB")
        source_size=image.size
        if min(source_size)<192:
            raise ReconstructionError("Choose a room photograph at least 192 pixels wide and high.")
        image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
        rgb=np.asarray(image)
    h,w=rgb.shape[:2]
    depth=_depth(rgb)
    Image.fromarray(np.uint8(depth*255)).save(output_dir/"depth.png")
    np.save(output_dir/"relative_depth.npy",depth,allow_pickle=False)
    lines=_lines(rgb)
    _report(progress,cancelled,"Fitting floor, wall planes and visible room boundaries")
    layout=_layout(rgb,depth,lines)
    camera=_camera(layout,w,h)
    objects,object_masks,wall_clean=_regions(rgb,depth,layout,camera,lines)
    side_clean={}
    for wall_name in ("left","right"):
        side_objects,side_masks,clean=_regions(rgb,depth,layout,camera,lines,wall_name=wall_name)
        objects.extend(side_objects);object_masks.extend(side_masks);side_clean[wall_name]=clean
    openings=_openings(rgb,depth,layout,camera,wall_clean)
    _report(progress,cancelled,"Extracting source materials and structured object geometry")
    width,height,room_depth=camera["width"],camera["height"],camera["depth"]
    xl,xr,yt,yb=layout["corners"]
    yy,xx=np.mgrid[:h,:w]
    ceiling_mask=((yy<yt)&(xx>xl)&(xx<xr)).astype(np.uint8)
    left_mask=side_clean["left"]
    right_mask=side_clean["right"]
    floor_mask=layout["floor_mask"]
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    texture_variation=float(np.std((gray.astype(np.float32)-cv2.GaussianBlur(gray.astype(np.float32),(0,0),3))[floor_mask.astype(bool)]))
    floor_kind="flake" if texture_variation>13 and np.mean(rgb[floor_mask.astype(bool)])<170 else "floor"
    materials={
        "floor":{"color":_color(rgb,floor_mask),"roughness":.4 if floor_kind=="flake" else .65,"metalness":.03,"kind":floor_kind,"texture_tile_size":.8},
        "wall":{"color":_color(rgb,wall_clean),"roughness":.82,"metalness":0.,"kind":"paint"},
        "wall-left":{"color":_color(rgb,left_mask,wall_clean.astype(bool)),"roughness":.82,"kind":"paint"},
        "wall-right":{"color":_color(rgb,right_mask,wall_clean.astype(bool)),"roughness":.82,"kind":"paint"},
        "ceiling":{"color":_color(rgb,ceiling_mask,wall_clean.astype(bool)),"roughness":.9,"kind":"paint"},
        # Behind the source camera there are no observed pixels to project.
        # A finish-only estimated closure keeps the walkable room coherent.
        "unseen-wall":{"color":_color(rgb,wall_clean),"roughness":.82,"metalness":0.,"kind":"estimated_paint"},
    }
    floor_texture,tile_size=_floor_patch(rgb,floor_mask,camera,output_dir)
    if floor_texture:
        materials["floor"]["texture"]=floor_texture
        materials["floor"]["texture_tile_size"]=tile_size
    # Rectify each independently fitted surface rather than wrapping the entire
    # reference around a room. Foreground object pixels are removed first.
    clean_rgb=rgb.copy()
    for mask,_ in object_masks:
        clean_rgb[mask.astype(bool)]=np.uint8(np.array(materials["wall"]["color"])*255)
    surface_points={
        "wall":[[-width/2,height,-room_depth/2],[width/2,height,-room_depth/2],[width/2,0,-room_depth/2],[-width/2,0,-room_depth/2]],
        "wall-left":[[-width/2,height,room_depth/2],[-width/2,height,-room_depth/2],[-width/2,0,-room_depth/2],[-width/2,0,room_depth/2]],
        "wall-right":[[width/2,height,-room_depth/2],[width/2,height,room_depth/2],[width/2,0,room_depth/2],[width/2,0,-room_depth/2]],
    }
    for name,points in surface_points.items():
        materials[name]["texture"]=_surface_texture(clean_rgb,camera,output_dir,name,points,materials[name]["color"])
        materials[name]["texture_repeat"]=False
    for i,opening in enumerate(openings):
        bbox=opening.pop("_source_bbox",None)
        if opening["kind"]=="window" and bbox:
            x1,y1,x2,y2=bbox
            mask=np.zeros((h,w),np.uint8);mask[y1:y2,x1:x2]=1
            texture=_patch(rgb,mask,output_dir,f"window-{i+1}",rect=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
            name=f"window-{i+1}"
            materials[name]={"color":_color(rgb,mask),"roughness":.15,"kind":"glass","texture":texture,"texture_repeat":False}
            opening["material"]=name
    for obj,(mask,bbox) in zip(objects,object_masks):
        materials[obj["material"]]={"color":_color(rgb,mask),"roughness":.42 if obj["kind"]=="cabinet" else .66,"metalness":.12 if obj["kind"]=="cabinet" else 0,"kind":"paint"}
        x1,y1,x2,y2=bbox
        # Preserve the source front on a separate material while real box sides
        # remain coherent geometry with a finish sampled from the same object.
        texture=_patch(rgb,mask,output_dir,obj["id"]+"-front",rect=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
        if texture:
            name=obj["id"]+"-front"
            materials[name]={**materials[obj["material"]],"texture":texture,"texture_repeat":False}
            obj["front_material"]=name
    walls=[
        {"id":"back","start":[-width/2,-room_depth/2],"end":[width/2,-room_depth/2],"height":height,"material":"wall","openings":openings},
        {"id":"left","start":[-width/2,room_depth/2],"end":[-width/2,-room_depth/2],"height":height,"material":"wall-left","openings":[]},
        {"id":"right","start":[width/2,-room_depth/2],"end":[width/2,room_depth/2],"height":height,"material":"wall-right","openings":[]},
        {"id":"front-estimated","start":[width/2,room_depth/2],"end":[-width/2,room_depth/2],"height":height,"material":"unseen-wall","openings":[]},
    ]
    warnings=["Dimensions are estimates anchored to an assumed 2.7 m ceiling; a single photograph cannot establish metric scale.",
              "Hidden geometry, furniture backs and surfaces behind the camera are unobserved estimates. Only box-like major objects are supported.",
              "The wall behind the source camera is an estimated solid closure with a sampled wall finish; its actual shape, openings and details are unknown.",
              "Source lighting is partly baked into photographed finishes; browser reflections and unseen materials are approximations.",
              "The confidence score measures floor/edge support, not photographic fidelity or semantic accuracy. Review the photo comparison and detected regions."]
    if layout["corner_sides"]<2:
        warnings.append("One or both outer wall corners are cropped. Side-wall positions require review in the correction controls.")
    if not layout["ceiling_visible"]:
        warnings.append("A wall/ceiling junction was not established. The ceiling is left open instead of placing an unsupported low roof.")
    if layout["votes"]<3:
        warnings.append("Weak vanishing-point evidence: camera field of view uses a 67 degree horizontal prior. Check camera alignment.")
    if not objects:
        warnings.append("No major cabinet-like foreground rectangles were reliably separated. Furniture visible in the image may be omitted; inspect the photo comparison and try a clearer, less occluded photo before relying on this walkthrough.")
    elif any(o["confidence"]<.65 for o in objects):
        warnings.append("Object semantics and depth are uncertain. Review detected cabinet/box positions and dimensions; small objects are omitted.")
    if openings:
        warnings.append("Detected openings are geometric hypotheses; review them before using the model for planning.")
    confidence=min(.72,.32+.24*layout["floor_support"]+.08*layout["corner_sides"]+.015*min(8,layout["votes"]))
    position=camera["position"].tolist();target=camera["target"].tolist()
    walk=[float(position[0]),min(1.65,height-.25),float(position[2])]
    scene={"schema_version":1,"units":"estimated_meters",
           "room":{"width":width,"depth":room_depth,"height":height,"floor_polygon":[[-width/2,-room_depth/2],[width/2,-room_depth/2],[width/2,room_depth/2],[-width/2,room_depth/2]],
                   "walls":walls,"ceiling":layout["ceiling_visible"],"floor_material":"floor","ceiling_material":"ceiling"},
           "camera":{"position":position,"target":target,"fov":camera["fov"],"fov_axis":"vertical","aspect":w/h},
           "walk_start":{"position":walk,"target":[target[0],walk[1]+target[1]-position[1],target[2]]},
           "objects":objects,"materials":materials,
           "source":{"image_path":source_path.name,"width":source_size[0],"height":source_size[1],"sha256":hashlib.sha256(source_path.read_bytes()).hexdigest()},
           "analysis":{"confidence":round(confidence,3),"warnings":warnings,"method":"depth-anything-v2-small + affine inverse-depth RANSAC + LSD Manhattan line/layout fitting + rectangular region analysis (CPU)",
                       "diagnostics":{"depth":"depth.png","overlay":"analysis-overlay.jpg","floor_mask":"floor-mask.png","wall_mask":"wall-mask.png",
                                      "image_corners":[[xl,yt],[xr,yt],[xr,yb],[xl,yb]],"vanishing_point":list(layout["vp"]),
                                      "analysis_size":[w,h],"floor_inlier_ratio":layout["floor_support"],"floor_coverage":layout["floor_coverage"],
                                      "line_count":len(lines),"vanishing_point_votes":layout["votes"],"object_count":len(objects),
                                      "inverse_depth_floor_plane":layout["floor_plane"].tolist(),"focal_length_pixels":camera["f"],
                                      "camera_pitch_radians":camera["pitch"],"floor_high_frequency_std":texture_variation}}}
    scene=validate_scene(scene)
    Image.fromarray(floor_mask*255).save(output_dir/"floor-mask.png")
    Image.fromarray(wall_clean*255).save(output_dir/"wall-mask.png")
    overlay=rgb.copy()
    tint=np.zeros_like(rgb);tint[:,:,1]=170
    overlay[floor_mask.astype(bool)]=(overlay[floor_mask.astype(bool)]*.7+tint[floor_mask.astype(bool)]*.3).astype(np.uint8)
    cv2.rectangle(overlay,(int(xl),int(yt)),(int(xr),int(yb)),(255,180,30),2)
    cv2.circle(overlay,tuple(map(int,layout["vp"])),7,(255,30,80),2)
    for obj,(_,box) in zip(objects,object_masks):
        x1,y1,x2,y2=box
        cv2.rectangle(overlay,(x1,y1),(x2,y2),(30,220,255),2)
        cv2.putText(overlay,obj["kind"],(x1,max(18,y1-4)),cv2.FONT_HERSHEY_SIMPLEX,.5,(30,220,255),1,cv2.LINE_AA)
    Image.fromarray(overlay).save(output_dir/"analysis-overlay.jpg",quality=92)
    (output_dir/"scene.json").write_text(json.dumps(scene,indent=2),encoding="utf-8")
    _report(progress,cancelled,"Photo analysis complete; preparing Blender meshes")
    return scene


def apply_corrections(scene: dict, corrections: dict) -> dict:
    """Apply bounded optional user edits without discarding image-derived assets."""
    import copy
    result=copy.deepcopy(validate_scene(scene))
    allowed={"room","camera","wall_corners","objects"}
    if not isinstance(corrections,dict) or set(corrections)-allowed:
        raise ReconstructionError("Unknown correction fields.")
    room=result["room"]
    updates=corrections.get("room",{})
    if set(updates)-{"width","depth","height"}:
        raise ReconstructionError("Only room width, depth and height may be corrected.")
    ratios={axis:float(updates.get(axis,room[axis]))/room[axis] for axis in ("width","height","depth")}
    if any(not math.isfinite(v) or v<.15 or v>6 for v in ratios.values()):
        raise ReconstructionError("Room corrections must stay within six times the estimate.")
    sx,sy,sz=ratios["width"],ratios["height"],ratios["depth"]
    for axis in ratios:
        room[axis]*=ratios[axis]
    room["floor_polygon"]=[[x*sx,z*sz] for x,z in room["floor_polygon"]]
    for wall in room["walls"]:
        old_length=math.dist(wall["start"],wall["end"])
        wall["start"]=[wall["start"][0]*sx,wall["start"][1]*sz]
        wall["end"]=[wall["end"][0]*sx,wall["end"][1]*sz]
        wall["height"]*=sy
        scale=math.dist(wall["start"],wall["end"])/old_length
        for opening in wall["openings"]:
            opening["offset"]*=scale;opening["width"]*=scale
            opening["height"]*=sy;opening["bottom"]*=sy
    for obj in result["objects"]:
        obj["position"]=[obj["position"][0]*sx,obj["position"][1]*sy,obj["position"][2]*sz]
        angle=obj["rotation_y"]
        local_width=math.hypot(math.cos(angle)*sx,math.sin(angle)*sz)
        local_depth=math.hypot(math.sin(angle)*sx,math.cos(angle)*sz)
        obj["dimensions"]=[obj["dimensions"][0]*local_width,obj["dimensions"][1]*sy,obj["dimensions"][2]*local_depth]
        obj["rotation_y"]=math.atan2(math.sin(angle)*sz,math.cos(angle)*sx)
    for key in ("camera","walk_start"):
        for prop in ("position","target"):
            x,y,z=result[key][prop];result[key][prop]=[x*sx,y*sy,z*sz]
    corners=corrections.get("wall_corners")
    if corners is not None:
        if not isinstance(corners,list) or len(corners)!=len(room["floor_polygon"]):
            raise ReconstructionError("Wall corners must match the existing floor polygon.")
        old=room["floor_polygon"]
        new=np.asarray(corners,dtype=float)
        if new.shape!=(len(old),2) or not np.isfinite(new).all() or np.abs(new).max()>50:
            raise ReconstructionError("Invalid wall corner coordinates.")
        contour=new.astype(np.float32)
        if abs(cv2.contourArea(contour))<1 or not cv2.isContourConvex(contour):
            raise ReconstructionError("Wall corners must form a convex room at least one square metre in area.")
        for wall in room["walls"]:
            old_start=wall["start"];old_end=wall["end"]
            length=math.dist(old_start,old_end)
            for prop in ("start","end"):
                nearest=min(range(len(old)),key=lambda i:math.dist(old[i],wall[prop]))
                if math.dist(old[nearest],wall[prop])<.02:
                    wall[prop]=new[nearest].tolist()
            scale=math.dist(wall["start"],wall["end"])/length
            for opening in wall["openings"]:
                opening["offset"]*=scale;opening["width"]*=scale
            # Keep wall-attached object locations consistent with the edited edge.
            direction=np.array(old_end)-old_start;den=float(direction@direction)
            new_direction=np.array(wall["end"])-wall["start"]
            for obj in result["objects"]:
                if obj.get("wall_id")==wall["id"]:
                    point=np.array([obj["position"][0],obj["position"][2]])
                    along=float((point-np.array(old_start))@direction/max(den,1e-6))
                    old_on=np.array(old_start)+along*direction
                    old_normal=np.array([-direction[1],direction[0]])/max(math.sqrt(den),1e-6)
                    distance_from_wall=float((point-old_on)@old_normal)
                    new_normal=np.array([-new_direction[1],new_direction[0]])/max(float(np.linalg.norm(new_direction)),1e-6)
                    new_on=np.array(wall["start"])+along*new_direction
                    p=new_on+new_normal*distance_from_wall
                    obj["position"][0]=float(p[0]);obj["position"][2]=float(p[1])
                    obj["dimensions"][0]*=scale
                    obj["rotation_y"]-=math.atan2(new_direction[1],new_direction[0])-math.atan2(direction[1],direction[0])
        room["floor_polygon"]=new.tolist()
        room["width"]=float(np.ptp(new[:,0]));room["depth"]=float(np.ptp(new[:,1]))
    cam_updates=corrections.get("camera",{})
    if set(cam_updates)-{"fov","pitch","position","target"}:
        raise ReconstructionError("Unknown camera correction fields.")
    for prop in ("fov","position","target"):
        if prop in cam_updates:
            result["camera"][prop]=cam_updates[prop]
    if "pitch" in cam_updates:
        pitch=float(cam_updates["pitch"])
        if not math.isfinite(pitch) or abs(pitch)>60:
            raise ReconstructionError("Camera pitch must be between -60 and 60 degrees.")
        pos=np.array(result["camera"]["position"]);target=np.array(result["camera"]["target"])
        length=max(1,float(np.linalg.norm(target-pos)))
        yaw=math.atan2(target[0]-pos[0],pos[2]-target[2]);pitch=math.radians(pitch)
        result["camera"]["target"]=(pos+length*np.array([math.sin(yaw)*math.cos(pitch),math.sin(pitch),-math.cos(yaw)*math.cos(pitch)])).tolist()
    edited=corrections.get("objects",[])
    by_id={obj["id"]:obj for obj in result["objects"]}
    if not isinstance(edited,list) or len(edited)>100:
        raise ReconstructionError("Object corrections must be a list.")
    for update in edited:
        if not isinstance(update,dict) or set(update)-{"id","position","dimensions","rotation_y"} or update.get("id") not in by_id:
            raise ReconstructionError("Object correction must refer to an existing object.")
        for prop in ("position","dimensions","rotation_y"):
            if prop in update:
                by_id[update["id"]][prop]=update[prop]
    result["analysis"]["warnings"].append("Room/camera/object geometry includes user corrections; source analysis diagnostics describe the original estimate.")
    return validate_scene(result)
