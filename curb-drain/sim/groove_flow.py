"""Stage 1: pressure-driven flow through a single groove cross-section.
Solves  laplacian(u) = -1  over the liquid region (Stokes flow along the groove),
u = 0 on wetted walls (no slip), du/dn = 0 on the free surface (no shear).
Conductance G = integral(u dA), so  Q = G * (-dp/ds) / mu.
"""
import numpy as np, scipy.sparse as sp, scipy.sparse.linalg as spla

def conductance(liquid, solid, h):
    """liquid/solid: boolean grids (anything else = air). h: cell size (m)."""
    idx = -np.ones(liquid.shape, int); idx[liquid] = np.arange(liquid.sum())
    n = liquid.sum(); rows, cols, vals = [], [], []
    diag = np.zeros(n)
    ny, nx = liquid.shape
    for (j, i), k in zip(zip(*np.nonzero(liquid)), idx[liquid]):
        for dj, di in ((1,0),(-1,0),(0,1),(0,-1)):
            jj, ii = j+dj, i+di
            if 0 <= jj < ny and 0 <= ii < nx and liquid[jj, ii]:
                rows.append(k); cols.append(idx[jj, ii]); vals.append(1.0); diag[k] -= 1
            elif 0 <= jj < ny and 0 <= ii < nx and solid[jj, ii]:
                diag[k] -= 2.0          # wall halfway between cell centres: u=0 there
            # air neighbour: zero-flux, contributes nothing
    A = sp.csr_matrix((vals + list(diag), (rows + list(range(n)), cols + list(range(n)))), (n, n))
    u = spla.spsolve(A, -np.ones(n) * h * h)
    return u.sum() * h * h

def grid(xmin, xmax, ymin, ymax, h):
    x = np.arange(xmin + h/2, xmax, h); y = np.arange(ymin + h/2, ymax, h)
    return np.meshgrid(x, y), h

if __name__ == "__main__":
    # validation: full pipe (pi R^4/8) and half pipe with free top (pi R^4/16)
    R = 1e-3
    for frac, ref, name in ((1, np.pi*R**4/8, "circular pipe"), (0.5, np.pi*R**4/16, "half pipe, free top")):
        (X, Y), h = grid(-1.2*R, 1.2*R, -1.2*R, 1.2*R, R/80)
        inside = X**2 + Y**2 < R**2
        liquid = inside & (Y < 0 if frac == 0.5 else True)
        solid = ~inside
        print(f"{name:22s} numeric/analytic = {conductance(liquid, solid, h)/ref:.3f}")
