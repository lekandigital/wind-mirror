"""3D lattice-Boltzmann wind tunnel (D3Q19, regularized BGK + Smagorinsky LES) on the GPU via Taichi.

x = streamwise (wind blows toward +x), y = lateral (periodic), z = up (free-slip floor and ceiling).
Solid cells use half-way bounce-back; the force on each labelled body part is measured by momentum exchange.
Everything is in lattice units; callers convert with the cell size.
"""
import time
import numpy as np
import taichi as ti



def ti_init():
    """Start Taichi on the GPU: CUDA on the box, Metal on a Mac. WM_ARCH=cpu forces the (slow) CPU backend."""
    import os
    arch = dict(cuda=ti.cuda, metal=ti.metal, vulkan=ti.vulkan, cpu=ti.cpu, gpu=ti.gpu)[os.environ.get('WM_ARCH', 'gpu')]
    ti.init(arch=arch, default_fp=ti.f32, device_memory_GB=float(os.environ.get('WM_MEM_GB', '6')), offline_cache=True)
    global FDT
    if ti.cfg.arch in (ti.metal, ti.vulkan):                 # these backends have no 64-bit floats: forces are summed in 32 bits there
        FDT = ti.f32


FDT = ti.f64                                                   # type of the force accumulator (64-bit on CUDA and CPU)


CX = (0, 1, -1, 0, 0, 0, 0, 1, -1, 1, -1, 1, -1, 1, -1, 0, 0, 0, 0)
CY = (0, 0, 0, 1, -1, 0, 0, 1, -1, -1, 1, 0, 0, 0, 0, 1, -1, 1, -1)
CZ = (0, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 1, -1, -1, 1, 1, -1, -1, 1)
W = (1 / 3,) + (1 / 18,) * 6 + (1 / 36,) * 12
OPP = (0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17)
_idx = {(CX[i], CY[i], CZ[i]): i for i in range(19)}
MZ = tuple(_idx[(CX[i], CY[i], -CZ[i])] for i in range(19))  # mirror in z (free-slip)


@ti.data_oriented
class Tunnel:
    def __init__(self, nx, ny, nz, U=0.08, nu=4e-4, cs_smag=0.14, nparts=40, soa=True):
        self.nx, self.ny, self.nz = nx, ny, nz
        self.U, self.nu = U, nu
        self.tau0 = 0.5 + 3.0 * nu
        self.cs2 = cs_smag * cs_smag
        self.nparts = nparts
        # structure-of-arrays layout: measured 5,380 million cell updates/s on the RTX 3090 Ti against 1,570 for the default layout (same results)
        lay = ti.Layout.SOA if soa else ti.Layout.AOS
        self.f = ti.Vector.field(19, ti.f32, shape=(nx, ny, nz), layout=lay)
        self.g = ti.Vector.field(19, ti.f32, shape=(nx, ny, nz), layout=lay)
        self.solid = ti.field(ti.u8, shape=(nx, ny, nz))
        self.force = ti.field(FDT, shape=(nparts, 3))
        self.vel = ti.Vector.field(3, ti.f32, shape=(nx, ny, nz))
        self.vavg = ti.Vector.field(3, ti.f32, shape=(nx, ny, nz))
        self.rho = ti.field(ti.f32, shape=(nx, ny, nz))
        self.ravg = ti.field(ti.f32, shape=(nx, ny, nz))      # running sum of (density - 1), for the mean pressure field
        usq = U * U
        self.feq_in = ti.Vector([W[i] * (1.0 + 3.0 * CX[i] * U + 4.5 * (CX[i] * U) ** 2 - 1.5 * usq) for i in range(19)])
        self.steps = 0

    @ti.kernel
    def reset(self):
        for I in ti.grouped(self.f):
            self.f[I] = self.feq_in
            self.g[I] = self.feq_in
            self.vavg[I] = ti.Vector([0.0, 0.0, 0.0])
            self.ravg[I] = 0.0

    @ti.kernel
    def clear_force(self):
        for p, k in self.force:
            self.force[p, k] = 0.0

    @ti.kernel
    def _step(self, fa: ti.template(), fb: ti.template(), acc: ti.i32):
        nx, ny, nz = self.nx, self.ny, self.nz
        tau0 = ti.cast(self.tau0, ti.f32)
        cs2 = ti.cast(self.cs2, ti.f32)
        for x, y, z in fa:
            if self.solid[x, y, z] == 0:
                if x == 0:
                    fb[x, y, z] = self.feq_in
                elif x < nx - 1:
                    fl = ti.Vector.zero(ti.f32, 19)
                    for i in ti.static(range(19)):
                        sx = x - CX[i]
                        sy = (y - CY[i] + ny) % ny
                        sz = z - CZ[i]
                        v = 0.0
                        if sz < 0 or sz >= nz:
                            if self.solid[sx, sy, z] != 0:
                                v = fa[x, y, z][OPP[i]]
                            else:
                                v = fa[sx, sy, z][MZ[i]]
                        else:
                            s = self.solid[sx, sy, sz]
                            if s != 0:
                                v = fa[x, y, z][OPP[i]]
                                if acc != 0:
                                    dv = ti.cast(2.0 * (v - W[i]), FDT)
                                    if ti.static(CX[i] != 0):
                                        self.force[s - 1, 0] += -dv * CX[i]
                                    if ti.static(CY[i] != 0):
                                        self.force[s - 1, 1] += -dv * CY[i]
                                    if ti.static(CZ[i] != 0):
                                        self.force[s - 1, 2] += -dv * CZ[i]
                            else:
                                v = fa[sx, sy, sz][i]
                        fl[i] = v
                    rho = fl.sum()
                    ux = 0.0
                    uy = 0.0
                    uz = 0.0
                    for i in ti.static(range(19)):
                        if ti.static(CX[i] != 0):
                            ux += CX[i] * fl[i]
                        if ti.static(CY[i] != 0):
                            uy += CY[i] * fl[i]
                        if ti.static(CZ[i] != 0):
                            uz += CZ[i] * fl[i]
                    inv = 1.0 / rho
                    ux *= inv
                    uy *= inv
                    uz *= inv
                    usq = ux * ux + uy * uy + uz * uz
                    feq = ti.Vector.zero(ti.f32, 19)
                    pxx = 0.0
                    pyy = 0.0
                    pzz = 0.0
                    pxy = 0.0
                    pxz = 0.0
                    pyz = 0.0
                    for i in ti.static(range(19)):
                        cu = CX[i] * ux + CY[i] * uy + CZ[i] * uz
                        fe = W[i] * rho * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * usq)
                        feq[i] = fe
                        d = fl[i] - fe
                        if ti.static(CX[i] != 0):
                            pxx += d
                        if ti.static(CY[i] != 0):
                            pyy += d
                        if ti.static(CZ[i] != 0):
                            pzz += d
                        if ti.static(CX[i] * CY[i] != 0):
                            pxy += CX[i] * CY[i] * d
                        if ti.static(CX[i] * CZ[i] != 0):
                            pxz += CX[i] * CZ[i] * d
                        if ti.static(CY[i] * CZ[i] != 0):
                            pyz += CY[i] * CZ[i] * d
                    qn = ti.sqrt(pxx * pxx + pyy * pyy + pzz * pzz + 2.0 * (pxy * pxy + pxz * pxz + pyz * pyz))
                    tau = 0.5 * (tau0 + ti.sqrt(tau0 * tau0 + 25.4558441 * cs2 * qn * inv))
                    om = 1.0 - 1.0 / tau
                    tr = (pxx + pyy + pzz) / 3.0
                    out = ti.Vector.zero(ti.f32, 19)
                    for i in ti.static(range(19)):
                        q = (CX[i] * CX[i]) * pxx + (CY[i] * CY[i]) * pyy + (CZ[i] * CZ[i]) * pzz \
                            + 2.0 * ((CX[i] * CY[i]) * pxy + (CX[i] * CZ[i]) * pxz + (CY[i] * CZ[i]) * pyz) - tr
                        out[i] = feq[i] + om * 4.5 * W[i] * q
                    fb[x, y, z] = out

    @ti.kernel
    def _outflow(self, fb: ti.template()):
        nx = self.nx
        for y, z in ti.ndrange(self.ny, self.nz):
            if self.solid[nx - 1, y, z] == 0:
                fb[nx - 1, y, z] = fb[nx - 2, y, z]

    def step(self, n=1, acc=False):
        a = 1 if acc else 0
        for _ in range(n):
            if self.steps % 2 == 0:
                self._step(self.f, self.g, a)
                self._outflow(self.g)
            else:
                self._step(self.g, self.f, a)
                self._outflow(self.f)
            self.steps += 1

    @ti.kernel
    def _macro(self, fa: ti.template(), accumulate: ti.i32):
        for x, y, z in fa:
            if self.solid[x, y, z] == 0:
                fl = fa[x, y, z]
                rho = fl.sum()
                u = ti.Vector([0.0, 0.0, 0.0])
                for i in ti.static(range(19)):
                    u += ti.Vector([CX[i], CY[i], CZ[i]]) * fl[i]
                u /= rho
                self.vel[x, y, z] = u
                self.rho[x, y, z] = rho
                if accumulate != 0:
                    self.vavg[x, y, z] += u
                    self.ravg[x, y, z] += rho - 1.0
            else:
                self.vel[x, y, z] = ti.Vector([0.0, 0.0, 0.0])
                self.rho[x, y, z] = 1.0

    def macro(self, accumulate=False):
        self._macro(self.f if self.steps % 2 == 0 else self.g, 1 if accumulate else 0)

    def set_solid(self, mask_u8):
        self.solid.from_numpy(np.ascontiguousarray(mask_u8, dtype=np.uint8))
        self.reset()
        self.clear_force()
        self.steps = 0

    def run(self, n_warm, n_avg, chunk=100, log=None, avg_field_every=0):
        """Returns mean force per part (lattice units, shape nparts x 3) and the drag time series."""
        self.step(n_warm, acc=False)
        series = []
        total = np.zeros((self.nparts, 3))
        done = 0
        nfield = 0
        while done < n_avg:
            n = min(chunk, n_avg - done)
            self.clear_force()
            self.step(n, acc=True)
            fr = self.force.to_numpy()
            total += fr
            series.append(fr[:, 0].sum() / n)
            done += n
            if avg_field_every and (done // chunk) % avg_field_every == 0:
                self.macro(accumulate=True)
                nfield += 1
            if log:
                log(done, series[-1])
        self.nfield = nfield
        return total / n_avg, np.array(series)

    def run2(self, n_warm, n_avg, chunk=100, fields=False):
        """Like run(), but also returns the total force vector per chunk (for a noise estimate on all three components)
        and, with fields=True, accumulates the mean velocity and density fields once per chunk (read them with mean_fields())."""
        self.step(n_warm, acc=False)
        total = np.zeros((self.nparts, 3))
        series = []
        done = 0
        self.nfield = 0
        while done < n_avg:
            n = min(chunk, n_avg - done)
            self.clear_force()
            self.step(n, acc=True)
            fr = self.force.to_numpy()
            total += fr
            series.append(fr.sum(0) / n)
            done += n
            if fields:
                self.macro(accumulate=True)
                self.nfield += 1
        return total / n_avg, np.array(series)

    def mean_fields(self, down=2):
        """Mean velocity (3) and mean (density - 1), block-averaged by `down` in each direction. Solid cells count as zero velocity."""
        n = max(self.nfield, 1)
        v = self.vavg.to_numpy() / n
        r = self.ravg.to_numpy() / n
        a = np.concatenate([v, r[..., None]], -1)
        nx, ny, nz = self.nx // down, self.ny // down, self.nz // down
        a = a[:nx * down, :ny * down, :nz * down].reshape(nx, down, ny, down, nz, down, 4).mean((1, 3, 5))
        return a
