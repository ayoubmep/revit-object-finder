# -*- coding: utf-8 -*-
"""Shaped parts for objects that have to be modelled, not found.

Plain boxes read as "blocks" in a render. These helpers give the forms that make a
piece look made: rounded corners, softened top edges, turned (lathe) shapes, tilted
cushions, half-round flutes, pleats, and thin plates at any angle.

    import shapes
    b = shapes.Builder(doc, floor_z=0.0, comment=u"my:room")
    b.soft(fabric, 2.4, 3.2, 5.2, 4.2, 0.04, 0.36, radius=0.18, bevel=0.04)      # sofa base
    b.soft(velvet, 2.5, 3.8, 3.1, 3.95, 0.5, 0.86, radius=0.05, bevel=0.03,
           tilt=("x", -12, (0, 3.95, 0.5)))                                       # leaning cushion
    b.lathe(glass, 8.0, 3.9, [(0.001, 1.3), (0.12, 1.36), (0.17, 1.47), (0.001, 1.47)])

Everything is in metres. `floor_z` is the absolute height of the floor the z values
are measured from. Each call makes one DirectShape carrying `comment`, so a whole
room can be found and deleted again. `mat` is a Revit Material.
"""
import math
try:
    from pyrevit.api import DB, UI
except ImportError:      # any other bridge that runs Python inside Revit
    import clr
    clr.AddReference('RevitAPI')
    clr.AddReference('RevitAPIUI')
    from Autodesk.Revit import DB, UI
from System.Collections.Generic import List

M = 1.0 / 0.3048
S45 = 0.70710678


class Builder(object):
    def __init__(self, doc, floor_z=0.0, comment=u"", category=None):
        self.doc = doc
        self.z0 = floor_z
        self.comment = comment
        self.category = category or DB.BuiltInCategory.OST_GenericModel

    # ------------------------------------------------------------ plumbing
    def _p(self, x, y, z):
        return DB.XYZ(x * M, y * M, (self.z0 + z) * M)

    def _options(self, mat):
        return DB.SolidOptions(mat.Id, DB.ElementId.InvalidElementId)

    def _emit(self, solids):
        shape = DB.DirectShape.CreateElement(self.doc, DB.ElementId(self.category))
        geometry = List[DB.GeometryObject]()
        for s in solids:
            geometry.Add(s)
        shape.SetShape(geometry)
        if self.comment:
            p = shape.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p and not p.IsReadOnly:
                p.Set(self.comment)
        return shape

    def _extrude(self, loop, height, mat):
        loops = List[DB.CurveLoop]()
        loops.Add(loop)
        return DB.GeometryCreationUtilities.CreateExtrusionGeometry(loops, DB.XYZ.BasisZ, height * M, self._options(mat))

    def _rect_loop(self, x1, y1, x2, y2, z, radius=0.0):
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        r = min(radius, 0.45 * (x2 - x1), 0.45 * (y2 - y1))
        loop = DB.CurveLoop()
        if r < 0.002:
            pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            for i in range(4):
                a, b = pts[i], pts[(i + 1) % 4]
                loop.Append(DB.Line.CreateBound(self._p(a[0], a[1], z), self._p(b[0], b[1], z)))
            return loop
        k = r * (1 - S45)
        corners = [((x1 + r, y1), (x2 - r, y1), (x2, y1 + r), (x2 - k, y1 + k)),
                   ((x2, y1 + r), (x2, y2 - r), (x2 - r, y2), (x2 - k, y2 - k)),
                   ((x2 - r, y2), (x1 + r, y2), (x1, y2 - r), (x1 + k, y2 - k)),
                   ((x1, y2 - r), (x1, y1 + r), (x1 + r, y1), (x1 + k, y1 + k))]
        for a, b, c, mid in corners:
            loop.Append(DB.Line.CreateBound(self._p(a[0], a[1], z), self._p(b[0], b[1], z)))
            loop.Append(DB.Arc.Create(self._p(b[0], b[1], z), self._p(c[0], c[1], z), self._p(mid[0], mid[1], z)))
        return loop

    def _tilt(self, solids, tilt):
        """tilt = (axis "x" | "y" | "z", degrees, (px, py, pz) pivot)."""
        if not tilt:
            return solids
        axis = {"x": DB.XYZ.BasisX, "y": DB.XYZ.BasisY, "z": DB.XYZ.BasisZ}[tilt[0]]
        pivot = self._p(tilt[2][0], tilt[2][1], tilt[2][2])
        tf = DB.Transform.CreateRotationAtPoint(axis, tilt[1] * math.pi / 180.0, pivot)
        return [DB.SolidUtils.CreateTransformed(s, tf) for s in solids]

    # ------------------------------------------------------------ forms
    def box(self, mat, x1, y1, x2, y2, z1, z2):
        return self._emit([self._extrude(self._rect_loop(x1, y1, x2, y2, z1), z2 - z1, mat)])

    def slab(self, mat, x1, y1, x2, y2, z1, z2, radius=0.05, tilt=None):
        """A plate with rounded corners in plan: table tops, rugs, screens."""
        solid = self._extrude(self._rect_loop(x1, y1, x2, y2, z1, radius), z2 - z1, mat)
        return self._emit(self._tilt([solid], tilt))

    def soft(self, mat, x1, y1, x2, y2, z1, z2, radius=0.08, bevel=0.04, steps=7, tilt=None):
        """An upholstered block: rounded in plan, with the top edge eased over `bevel`."""
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        bevel = min(bevel, 0.45 * (z2 - z1), 0.3 * (x2 - x1), 0.3 * (y2 - y1))
        solids = [self._extrude(self._rect_loop(x1, y1, x2, y2, z1, radius), z2 - z1 - bevel, mat)]
        low = z2 - bevel
        for i in range(1, steps + 1):
            a0 = (i - 1) * math.pi / (2.0 * steps)
            a1 = i * math.pi / (2.0 * steps)
            inset = bevel * (1 - math.cos(a1))
            za = low + bevel * math.sin(a0)
            zb = low + bevel * math.sin(a1)
            loop = self._rect_loop(x1 + inset, y1 + inset, x2 - inset, y2 - inset, za, max(radius - inset, 0.01))
            solids.append(self._extrude(loop, zb - za, mat))
        return self._emit(self._tilt(solids, tilt))

    def _lathe_solid(self, mat, x, y, profile):
        frame = DB.Frame(self._p(x, y, 0.0), DB.XYZ.BasisX, DB.XYZ.BasisY, DB.XYZ.BasisZ)
        loop = DB.CurveLoop()
        n = len(profile)
        for i in range(n):
            r0, z0 = profile[i]
            r1, z1 = profile[(i + 1) % n]
            loop.Append(DB.Line.CreateBound(self._p(x + max(r0, 0.001), y, z0), self._p(x + max(r1, 0.001), y, z1)))
        loops = List[DB.CurveLoop]()
        loops.Add(loop)
        return DB.GeometryCreationUtilities.CreateRevolvedGeometry(frame, loops, 0.0, 2 * math.pi, self._options(mat))

    def lathe(self, mat, x, y, profile):
        """A turned shape: `profile` is a closed outline of (radius, z) points, revolved
        around the vertical axis at (x, y). Vases, lamp shades, round bases, bowls."""
        return self._emit([self._lathe_solid(mat, x, y, profile)])

    def lathes(self, mat, pieces):
        """Many turned shapes as one element: `pieces` is a list of (x, y, profile)."""
        return self._emit([self._lathe_solid(mat, x, y, profile) for x, y, profile in pieces])

    def cylinder(self, mat, x, y, radius, z1, z2):
        return self.lathe(mat, x, y, [(0.0, z1), (radius, z1), (radius, z2), (0.0, z2)])

    def dome(self, mat, x, y, radius, z_bottom, segments=8):
        """A solid half-sphere with its flat face up: a bowl-shaped lamp shade."""
        profile = [(0.0, z_bottom)]
        for i in range(1, segments + 1):
            a = i * math.pi / (2.0 * segments)
            profile.append((radius * math.sin(a), z_bottom + radius * (1 - math.cos(a))))
        profile.append((0.0, z_bottom + radius))
        return self.lathe(mat, x, y, profile)

    def flutes(self, mat, x1, x2, y_face, z1, z2, pitch=0.07, radius=0.03, toward=-1):
        """Half-round vertical ribs along X on a wall face at y_face, bulging toward
        -Y (toward=-1) or +Y. One element for the whole run."""
        solids = []
        x = x1 + radius
        while x + radius <= x2 + 1e-6:
            loop = DB.CurveLoop()
            a = self._p(x - radius, y_face, z1)
            b = self._p(x + radius, y_face, z1)
            mid = self._p(x, y_face + toward * radius, z1)
            if toward < 0:
                loop.Append(DB.Line.CreateBound(a, b))
                loop.Append(DB.Arc.Create(b, a, mid))
            else:
                loop.Append(DB.Line.CreateBound(b, a))
                loop.Append(DB.Arc.Create(a, b, mid))
            solids.append(self._extrude(loop, z2 - z1, mat))
            x += pitch
        return self._emit(solids)

    def pleats(self, mat, x1, x2, y, z1, z2, pitch=0.08, radius=0.045):
        """A curtain: a row of overlapping round folds along X. One element."""
        solids = []
        x = x1 + radius
        while x + radius <= x2 + 1e-6:
            solids.append(self._lathe_solid(mat, x, y, [(0.0, z1), (radius, z1), (radius, z2), (0.0, z2)]))
            x += pitch
        return self._emit(solids)

    def plates(self, mat, pieces):
        """Thin plates or bars at any angle, as one element. Each piece is
        (cx, cy, cz, size_x, size_y, size_z, rot_x, rot_y, rot_z) with angles in degrees,
        applied in that order around the piece's own centre."""
        solids = []
        for cx, cy, cz, sx, sy, sz, rx, ry, rz in pieces:
            loop = DB.CurveLoop()
            hx, hy = sx * M / 2.0, sy * M / 2.0
            pts = [DB.XYZ(-hx, -hy, -sz * M / 2.0), DB.XYZ(hx, -hy, -sz * M / 2.0),
                   DB.XYZ(hx, hy, -sz * M / 2.0), DB.XYZ(-hx, hy, -sz * M / 2.0)]
            for i in range(4):
                loop.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
            loops = List[DB.CurveLoop]()
            loops.Add(loop)
            solid = DB.GeometryCreationUtilities.CreateExtrusionGeometry(loops, DB.XYZ.BasisZ, sz * M, self._options(mat))
            tf = DB.Transform.CreateTranslation(self._p(cx, cy, cz))
            for axis, angle in ((DB.XYZ.BasisZ, rz), (DB.XYZ.BasisY, ry), (DB.XYZ.BasisX, rx)):
                if angle:
                    tf = tf.Multiply(DB.Transform.CreateRotation(axis, angle * math.pi / 180.0))
            solids.append(DB.SolidUtils.CreateTransformed(solid, tf))
        return self._emit(solids)
