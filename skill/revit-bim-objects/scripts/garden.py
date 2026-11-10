# -*- coding: utf-8 -*-
"""Garden and street pieces with natural, turned forms (no boxes).

Real plants with modelled leaves are fetched and enlarged with the object fetcher
(`polyhaven.add(..., scale=3)` turns a 1.5 m aloe tree into a 4.5 m garden tree).
This module covers what a catalogue does not: columnar cypresses, round shrubs and
lavender tufts, garden lights, a parasol, stools and street lamps. Each takes a
`shapes.Builder` and Revit materials; positions are in metres.
"""
import math


def _wobble(seed, i):
    return ((seed * 37 + i * 91) % 17) / 17.0 - 0.5


def ellipsoid(cz, rx, rz, n=8):
    """Profile of a rounded blob centred at height cz."""
    pts = [(0.0, cz - rz)]
    for i in range(1, n):
        a = i * math.pi / n
        pts.append((rx * math.sin(a), cz - rz * math.cos(a)))
    pts.append((0.0, cz + rz))
    return pts


def cypress(b, leaf, trunk, x, y, height=6.5, radius=0.6, seed=0):
    """A columnar cypress: short trunk, tall tapering crown with an uneven outline."""
    b.cylinder(trunk, x, y, 0.09, 0.0, 0.9)
    base = 0.55
    pts = [(0.0, base)]
    n = 14
    for i in range(1, n):
        t = i / float(n)
        r = radius * math.sqrt(4 * t * (1 - t)) * (1.18 - 0.62 * t) + 0.07 * radius * _wobble(seed, i)
        pts.append((max(r, 0.04), base + t * (height - base)))
    pts.append((0.0, height))
    return b.lathe(leaf, x, y, pts)


def shrub(b, leaf, x, y, radius=0.6, seed=0):
    """A clipped round shrub made of a few overlapping domes."""
    pieces = [(x, y, ellipsoid(radius * 0.8, radius, radius * 0.8))]
    for i in range(4):
        a = i * 1.7 + seed
        r = radius * (0.55 + 0.15 * _wobble(seed, i))
        pieces.append((x + 0.55 * radius * math.cos(a), y + 0.55 * radius * math.sin(a), ellipsoid(r * 0.85, r, r * 0.8)))
    return b.lathes(leaf, pieces)


def tufts(b, mat, points, radius=0.24, height=0.42):
    """Low rounded tufts (lavender, grasses) at the given (x, y) points, one element."""
    pieces = []
    for i, (x, y) in enumerate(points):
        r = radius * (1 + 0.25 * _wobble(i, 3))
        pieces.append((x, y, ellipsoid(height / 2.0, r, height / 2.0, 6)))
    return b.lathes(mat, pieces)


def bollard(b, body, light, x, y, height=0.55):
    b.cylinder(body, x, y, 0.045, 0.0, height - 0.07)
    b.cylinder(light, x, y, 0.05, height - 0.07, height - 0.02)
    b.cylinder(body, x, y, 0.055, height - 0.02, height)


def parasol(b, fabric, pole, x, y, radius=1.6, height=2.5):
    b.cylinder(pole, x, y, 0.022, 0.0, height)
    b.lathe(pole, x, y, [(0.0, 0.0), (0.22, 0.0), (0.22, 0.03), (0.04, 0.06), (0.0, 0.06)])
    b.lathe(fabric, x, y, [(0.0, height - 0.02), (radius, height - 0.42), (radius, height - 0.46), (0.0, height - 0.1)])


def stool(b, fabric, x, y, radius=0.26, height=0.42):
    """A round upholstered stool with eased edges."""
    b.lathe(fabric, x, y, [(0.0, 0.0), (radius * 0.9, 0.0), (radius, 0.05), (radius, height - 0.07),
                           (radius * 0.9, height), (0.0, height)])


def street_lamp(b, body, light, x, y, toward=(0.0, -1.0), height=5.2, reach=1.1):
    """A tapered pole with an arm reaching `reach` metres in the `toward` direction."""
    b.lathe(body, x, y, [(0.0, 0.0), (0.11, 0.0), (0.09, 0.35), (0.05, height), (0.0, height)])
    ax, ay = toward
    yaw = math.degrees(math.atan2(ay, ax))
    b.plates(body, [(x + ax * reach / 2.0, y + ay * reach / 2.0, height - 0.05, reach, 0.06, 0.06, 0, 0, yaw)])
    b.plates(light, [(x + ax * (reach - 0.2), y + ay * (reach - 0.2), height - 0.11, 0.42, 0.16, 0.05, 0, 0, yaw)])
