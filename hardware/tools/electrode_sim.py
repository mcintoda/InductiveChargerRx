#!/usr/bin/env python3
"""2-D quasi-static field model of the level electrodes (vertical cross-section).

Solves  div((sigma + j*omega*eps) grad phi) = 0  on a non-uniform grid in the (h, z) plane:
  h = height along the board (0 = bottom of pad 1), z = through the board / wall / water.
Each electrode is driven in turn (1 V) and its admittance Y is integrated; C = Im(Y)/omega,
scaled by the 30 mm electrode width (2-D -> per-length x width; fringing at the
electrode's left/right ends is ignored, a few % effect).

Model (z = 0 is the electrode copper on L1, + towards the water):
  z  -1.6       battery pouch (conductor, 0 V) behind the PCB
  z  -1.0..0    FR-4 (er 4.4); hatched SHIELD on L2 at z = -0.2 (0.3 mm strips, 1 mm pitch)
  z   0..t_w    enclosure front wall (PC er 2.9, or PP er 2.2)
  z   t_w..8    water (er 80, sigma) below the water level, air above; optional water film
                (0.1 mm) on the wall above the waterline.  Water is tied to 0 V at the far
                boundary (it couples to the device ground through the rest of the
                submerged enclosure; this makes dC an upper bound by ~10-15 %).
Idle electrodes are either held at 0 V (ESP32-S3 TOUCH_PAD_CONN_GND) or follow the drive
waveform ("driven"): with TOUCH_PAD_CONN_HIGHZ a floating idle pad is pulled to the shield
potential by its ~10x larger coupling to the L2 shield, so "driven" approximates HIGHZ.
The shield is either driven (same waveform as the measured pad) or grounded.

    python3 hardware/tools/electrode_sim.py   ->  docs/img/electrode_*.png + printed tables
"""
import os

import matplotlib
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

E0 = 8.854e-12
F = 1e6                      # effective touch excitation frequency (order of magnitude)
W_PAD = 30e-3                # electrode width (x), m
PITCH, PAD_H = 10.0, 9.0
PADS = {f"PAD{k}": ((k - 1) * PITCH, (k - 1) * PITCH + PAD_H) for k in range(1, 7)}
PADS["REF"] = (63.0, 69.0)
GND_COPPER = [(-14.0, -2.0)]  # thermal-window copper on the tab below pad 1 (0 V)
IMG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "img")


def axis(segments):
    pts = [segments[0][0]]
    for a, b, d in segments:
        n = max(1, int(round((b - a) / d)))
        pts += list(np.linspace(a, b, n + 1)[1:])
    return np.array(pts)


class Model:
    def __init__(self, t_wall=1.2, er_wall=2.9, sigma=0.05, dh=0.25):
        self.t = t_wall
        self.h = axis([(-15.0, 85.0, dh)])
        self.z = axis([(-1.6, -1.0, 0.1), (-1.0, 0.0, 0.05), (0.0, t_wall, 0.05),
                       (t_wall, t_wall + 0.3, 0.05), (t_wall + 0.3, 8.0, 0.25)])
        self.er_wall, self.sigma = er_wall, sigma
        self.w = 2 * np.pi * F

    def cells(self, level, film=0.0, film_t=0.1):
        """Complex conductivity per cell (Nh-1, Nz-1)."""
        hc = 0.5 * (self.h[1:] + self.h[:-1])[:, None]
        zc = 0.5 * (self.z[1:] + self.z[:-1])[None, :]
        k = np.full((hc.shape[0], zc.shape[1]), 1j * self.w * E0 * 1.0, dtype=complex)  # air
        k = np.where((zc > -1.0) & (zc < 0.0), 1j * self.w * E0 * 4.4, k)              # FR-4
        k = np.where((zc > 0.0) & (zc < self.t), 1j * self.w * E0 * self.er_wall, k)    # wall
        water = self.sigma + 1j * self.w * E0 * 80
        k = np.where((zc > self.t) & (hc < level), water, k)
        if film > 0:
            k = np.where((zc > self.t) & (zc < self.t + film_t) & (hc >= level) & (hc < level + film), water, k)
        return k

    def solve(self, level, driven, shield="driven", film=0.0, idle="driven"):
        h, z = self.h, self.z
        nh, nz = len(h), len(z)
        idx = lambda i, j: i * nz + j  # noqa: E731
        k = self.cells(level, film)
        dh, dz = np.diff(h), np.diff(z)
        # Dirichlet nodes
        fixed = {}
        j0 = int(np.argmin(abs(z - 0.0)))
        js = int(np.argmin(abs(z + 0.2)))
        for i, hv in enumerate(h):
            fixed[idx(i, 0)] = 0.0                                     # battery
            if hv < level:
                fixed[idx(i, nz - 1)] = 0.0                            # bulk water
            for name, (a, b) in PADS.items():
                if a <= hv <= b:
                    fixed[idx(i, j0)] = 1.0 if (name == driven or idle == "driven") else 0.0
            for a, b in GND_COPPER:
                if a <= hv <= b:
                    fixed[idx(i, j0)] = 0.0
            if -0.5 <= hv <= 70.5 and (hv % 1.0) < 0.3 + 1e-9:          # hatched L2 shield
                fixed[idx(i, js)] = 1.0 if shield == "driven" else 0.0
        # assemble finite-volume conductances
        rows, cols, vals = [], [], []
        def edge(a, b, g):
            rows.extend([a, b, a, b]); cols.extend([a, b, b, a]); vals.extend([g, g, -g, -g])
        for i in range(nh):
            for j in range(nz):
                if i + 1 < nh:   # h-direction edge, weighted by adjacent cells' z extent
                    g = 0.0
                    if j > 0:
                        g += k[i, j - 1] * dz[j - 1] / 2
                    if j < nz - 1:
                        g += k[i, j] * dz[j] / 2
                    edge(idx(i, j), idx(i + 1, j), g / dh[i])
                if j + 1 < nz:
                    g = 0.0
                    if i > 0:
                        g += k[i - 1, j] * dh[i - 1] / 2
                    if i < nh - 1:
                        g += k[i, j] * dh[i] / 2
                    edge(idx(i, j), idx(i, j + 1), g / dz[j])
        N = nh * nz
        A = sp.csr_matrix((vals, (rows, cols)), shape=(N, N), dtype=complex)
        fx = np.array(sorted(fixed)); fv = np.array([fixed[n] for n in fx])
        free = np.setdiff1d(np.arange(N), fx)
        phi = np.zeros(N, dtype=complex); phi[fx] = fv
        rhs = -A[free][:, fx] @ fv
        phi[free] = spl.spsolve(A[free][:, free].tocsc(), rhs)
        # current out of the driven electrode = sum of its node residuals
        da, db = PADS[driven]
        drv = [n for n in fx if fixed[n] == 1.0 and n % nz == j0 and da <= h[n // nz] <= db]
        I = (A[drv] @ phi).sum()                       # per metre of depth (mm units cancel)
        return (I.imag / self.w) * W_PAD * 1e12        # pF


def dC(m, name, level, **kw):
    return m.solve(level, name, **kw) - m.solve(-14.9, name, **kw)


def main():
    os.makedirs(IMG, exist_ok=True)
    m = Model()
    names = [f"PAD{k}" for k in range(1, 7)] + ["REF"]
    base = {n: m.solve(-14.9, n) for n in names}
    print("Dry (baseline) capacitance per electrode, driven shield [pF]:",
          {n: round(v, 2) for n, v in base.items()})

    # 1) response vs level
    levels = np.arange(-5.0, 76.0, 1.0)
    resp = {n: np.array([m.solve(L, n) - base[n] for L in levels]) for n in names}
    full = resp["PAD1"][levels == 25.0][0]
    print(f"Full-wet dC (pad fully covered) = {full:.2f} pF")
    # level reconstruction (firmware): each pad's own full-wet dC is learned as the water passes it;
    # L = sum_k clamp(dC_k / dC_full,k) * pitch   (pad 1 bottom = 0)
    fullk = {k: resp[f"PAD{k}"].max() for k in range(1, 7)}
    est = sum(np.clip(resp[f"PAD{k}"] / fullk[k], 0, 1) for k in range(1, 7)) * PITCH
    sel = (levels >= 0) & (levels <= 59)
    bias = (est - np.clip(levels, 0, 60))[sel].mean()          # fixed fringe offset, a firmware constant
    print(f"Constant fringe offset removed: {bias:.2f} mm")
    est = np.where(est > 0, np.clip(est - bias, 0, 60), 0)
    err = est - np.clip(levels, 0, 60)
    print(f"Interpolated level error over 0..59 mm: max {abs(err[sel]).max():.2f} mm, rms {np.sqrt((err[sel]**2).mean()):.2f} mm")

    fig, ax = plt.subplots(2, 1, figsize=(7.5, 6.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.4]})
    for n in names:
        ax[0].plot(levels, resp[n], label=n, lw=1.6, ls="--" if n == "REF" else "-")
    ax[0].set_ylabel("dC vs dry [pF]"); ax[0].legend(ncol=4, fontsize=8, frameon=False)
    ax[0].set_title(f"Electrode response vs water level (30x9 mm pads, {m.t} mm PC wall, driven shield)", fontsize=10)
    ax[0].grid(alpha=0.3)
    ax[1].plot(levels, err, color="k", lw=1.4)
    ax[1].set_ylabel("level error [mm]"); ax[1].set_xlabel("water level above bottom of pad 1 [mm]")
    ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "electrode_response.png"), dpi=130); plt.close(fig)

    # 2) water film above the waterline: idle pads grounded vs following the shield (HIGHZ)
    L0 = 25.0  # waterline at the middle of pad 3
    films = [0, 5, 10, 20, 40]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for idle, ls in (("gnd", "--"), ("driven", "-")):
        b = {n: m.solve(-14.9, n, idle=idle) for n in ("PAD4", "PAD5")}
        fl = m.solve(25.0, "PAD1", idle=idle) - m.solve(-14.9, "PAD1", idle=idle)
        for n, c in (("PAD4", "C0"), ("PAD5", "C1")):
            y = [100 * (m.solve(L0, n, film=f, idle=idle) - b[n]) / fl for f in films]
            print(f"idle={idle}: {n} false signal [% full-wet] for film {films} mm: {[round(v, 1) for v in y]}")
            ax.plot(films, y, ls=ls, color=c, marker="o",
                    label=f"{n} ({'1st' if n == 'PAD4' else '2nd'} pad above water), idle pads {'GND' if idle == 'gnd' else 'HIGHZ/shield'}")
    ax.axhline(50, color="r", lw=0.8); ax.text(0.5, 52, "wet/dry decision threshold", color="r", fontsize=8)
    ax.set_xlabel("height of 0.1 mm water film above the waterline [mm]  (waterline at mid pad 3, 500 uS/cm)")
    ax.set_ylabel("false signal [% of full-wet]"); ax.grid(alpha=0.3); ax.legend(fontsize=7.5, frameon=False)
    ax.set_title("Run-off film on the wall: effect on dry pads", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "electrode_film.png"), dpi=130); plt.close(fig)
    print("Dry baseline PAD3: shield driven %.2f pF, shield grounded %.2f pF"
          % (m.solve(-14.9, "PAD3"), m.solve(-14.9, "PAD3", shield="ground")))

    # 3) wall material / thickness trade-off (full-wet dC of one pad)
    print("Full-wet dC per pad vs wall [pF]:")
    rows = []
    for name, er in (("PC", 2.9), ("PP", 2.2)):
        for t in (0.8, 1.2, 1.6, 2.0):
            mm_ = Model(t_wall=t, er_wall=er)
            v = mm_.solve(25.0, "PAD1") - mm_.solve(-14.9, "PAD1")
            rows.append((name, t, v)); print(f"  {name} {t} mm: {v:.2f}")
    return rows


if __name__ == "__main__":
    main()
