"""
Parametric structure-map renderer (v2 composition) for the ControlNet test.

Produces a 512x512 control image from a segmental spec — the structure the
generation must follow. At inference this replaces the real-diagram control
maps used in training. Same composition family: one cardiac silhouette with
great vessels emerging on top, systemic veins left, branch PAs right,
AV-valve ovals, descending-aorta bifurcation.

CLI:
  python3 training/render_control.py --loop L --va dorv --ps --out ctrl.png
"""
import argparse
import math
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch

SIZE = 512
LW = 2.6

def _catmull(pts, n=24, closed=False):
    pts = np.array(pts, float)
    pts = np.vstack([pts[-1] if closed else pts[0], pts, pts[0] if closed else pts[-1]])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i-1], pts[i], pts[i+1], pts[i+2]
        t = np.linspace(0, 1, n)[:, None]
        out.append(0.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t**2+(-p0+3*p1-3*p2+p3)*t**3))
    return np.vstack(out)

def _stroke(ax, pts, closed=False, lw=LW):
    ax.add_patch(PathPatch(MPath(_catmull(pts, closed=closed)), fc="none", ec="k", lw=lw))

def _tube(ax, pts, wd, lw=LW):
    c = _catmull(pts, 18); d = np.gradient(c, axis=0); L = np.hypot(d[:, 0], d[:, 1]); L[L == 0] = 1
    nrm = np.c_[-d[:, 1]/L, d[:, 0]/L]
    ax.add_patch(PathPatch(MPath(c+nrm*wd/2), fc="none", ec="k", lw=lw))
    ax.add_patch(PathPatch(MPath(c-nrm*wd/2), fc="none", ec="k", lw=lw))

def _oval(ax, cx, cy, rx, ry, ang=0):
    t = np.linspace(0, 2*math.pi, 40); a = math.radians(ang)
    x = cx + rx*np.cos(t)*math.cos(a) - ry*np.sin(t)*math.sin(a)
    y = cy + rx*np.cos(t)*math.sin(a) + ry*np.sin(t)*math.cos(a)
    ax.add_patch(PathPatch(MPath(np.c_[x, y]), fc="none", ec="k", lw=1.9))

def render_control(loop="D", va="concordant", ps=False) -> Image.Image:
    fig, ax = plt.subplots(figsize=(5.12, 5.12), dpi=100)

    silhouette = [(120,238),(78,258),(58,315),(74,378),(120,405),(180,420),
                  (255,428),(325,420),(385,392),(428,338),(438,285),(414,244),
                  (360,236),(322,250),(262,240),(196,232),(150,232)]
    _stroke(ax, silhouette, closed=True, lw=2.9)
    _stroke(ax, [(250,250),(248,320),(258,390)], lw=1.9)          # septum
    _oval(ax, 214, 286, 24, 11, ang=-20)                          # AV valves
    _oval(ax, 292, 286, 24, 11, ang=20)

    _tube(ax, [(92,30),(96,130),(112,232)], 34)                   # SVC
    _tube(ax, [(104,500),(102,430),(110,392)], 34)                # IVC
    for yy in (150,192,226):                                      # pulmonary veins
        _tube(ax, [(40,yy),(74,yy),(96,yy+2)], 20)

    if va == "dorv":   ao_root, pa_root = 300, 250
    elif va == "dtga": ao_root, pa_root = 250, 250
    else:              ao_root, pa_root = 232, 275

    _tube(ax, [(ao_root,250),(ao_root-6,180),(ao_root-4,120)], 30)   # ascending Ao
    arch = _catmull([(ao_root-4,120),(ao_root+30,72),(ao_root-30,60),(ao_root-96,74),
                     (ao_root-140,120),(ao_root-150,190),(ao_root-130,250)], 24)
    d = np.gradient(arch, axis=0); Ls = np.hypot(d[:,0],d[:,1]); Ls[Ls==0] = 1; nrm = np.c_[-d[:,1]/Ls, d[:,0]/Ls]
    ax.add_patch(PathPatch(MPath(arch+nrm*15), fc="none", ec="k", lw=LW))
    ax.add_patch(PathPatch(MPath(arch-nrm*15), fc="none", ec="k", lw=LW))
    for hx in (ao_root-24, ao_root-58, ao_root-92):                 # head vessels
        _tube(ax, [(hx,64),(hx-4,26)], 13)
    _tube(ax, [(ao_root-130,250),(292,360),(288,430)], 22)          # descending Ao
    _stroke(ax, [(288,430),(268,470),(268,500)], lw=LW)
    _stroke(ax, [(288,430),(308,470),(308,500)], lw=LW)

    _tube(ax, [(pa_root,250),(pa_root+8,190),(pa_root+14,150)], 30 if not ps else 17)  # MPA (PS=pinch)
    _tube(ax, [(pa_root+14,150),(330,150),(415,135)], 20)          # RPA
    _tube(ax, [(pa_root+14,150),(330,196),(408,205)], 20)          # LPA

    ax.set_xlim(0, SIZE); ax.set_ylim(0, SIZE); ax.invert_yaxis(); ax.set_aspect("equal"); ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1); fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[..., :3]; plt.close(fig)
    return Image.fromarray(buf).resize((SIZE, SIZE))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", default="D", choices=["D", "L"])
    ap.add_argument("--va", default="concordant", choices=["concordant", "dorv", "dtga"])
    ap.add_argument("--ps", action="store_true")
    ap.add_argument("--out", default="control.png")
    a = ap.parse_args()
    render_control(a.loop, a.va, a.ps).save(a.out)
    print("saved", a.out)
