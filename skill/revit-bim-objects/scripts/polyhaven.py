# -*- coding: utf-8 -*-
"""Fetch one 3D object at a time from Poly Haven and place it in Revit.

Poly Haven (https://polyhaven.com) publishes CC0 models and offers a public API meant
for this kind of use. Nothing is downloaded in bulk: `search` reads the catalogue,
and `add` downloads only the objects it is asked to place (a few hundred KB each).

    import polyhaven
    found = polyhaven.search(["armchair", "modern"])
    report = polyhaven.add(doc, [
        {"asset": "modern_arm_chair_01", "x": 6.2, "y": 3.2, "level": u"Niveau 1", "rotation": 200},
    ])

Coordinates are in metres, rotation in degrees counter-clockwise seen from above.

What you get is geometry, not a parametric Revit family: one DirectShape type per
object, instanced wherever it is placed, in the Furniture category. Revit cannot keep
a mesh's texture mapping, so each part is given one material in the average colour of
its texture. Trees and other objects that depend on their textures are a bad fit.

Poly Haven asks tools that use its API to say where the assets come from: every
instance is commented "Poly Haven: <id> (CC0)".
"""
import json
import math
import os
import struct
try:
    from pyrevit.api import DB, UI
except ImportError:      # any other bridge that runs Python inside Revit
    import clr
    clr.AddReference('RevitAPI')
    clr.AddReference('RevitAPIUI')
    from Autodesk.Revit import DB, UI
import System
from System.Collections.Generic import List

M = 1.0 / 0.3048
API = "https://api.polyhaven.com"
USER_AGENT = "revit-bim-objects-skill/0.1"
DEFAULT_FOLDER = "C:\\BIM-Library\\polyhaven"
PREFIX = u"PH - "
MAX_TRIANGLES = 60000

CATEGORIES = {
    "furniture": DB.BuiltInCategory.OST_Furniture,
    "lighting": DB.BuiltInCategory.OST_LightingFixtures,
    "plant": DB.BuiltInCategory.OST_Planting,
    "generic": DB.BuiltInCategory.OST_GenericModel,
}


# ---------------------------------------------------------------- web
def _client():
    import clr
    for assembly in ("System", "System.Net.WebClient"):      # .NET Framework / .NET 8
        try:
            clr.AddReference(assembly)
        except Exception:
            pass
    from System.Net import WebClient
    client = WebClient()
    client.Headers.Add("User-Agent", USER_AGENT)
    client.Encoding = System.Text.Encoding.UTF8
    return client


def _get_json(url):
    return json.loads(_client().DownloadString(url))


def search(words, max_polys=MAX_TRIANGLES):
    """Models whose id, name, tags or categories contain every word. Smallest first."""
    words = [w.lower() for w in words]
    out = []
    for asset_id, info in _get_json(API + "/assets?t=models").items():
        text = u" ".join([asset_id, info.get("name", u"")] + list(info.get("tags", [])) +
                         list(info.get("categories", []))).lower()
        if not all(w in text for w in words):
            continue
        polys = info.get("polycount") or 0
        if polys > max_polys:
            continue
        dims = info.get("dimensions") or [0, 0, 0]
        out.append({"asset": asset_id, "name": info.get("name"), "polycount": polys,
                    "size_m": [round(d / 1000.0, 2) for d in dims],
                    "categories": info.get("categories", [])})
    out.sort(key=lambda r: r["polycount"])
    return out


def preview_sheet(asset_ids, path="C:\\BIM-Library\\previews\\sheet.png", columns=5, cell=230):
    """Downloads the preview picture of each object and tiles them into one labelled
    image, so candidates can be compared with a reference by eye. Returns the path."""
    import clr
    clr.AddReference("System.Drawing")
    from System.Drawing import Bitmap, Graphics, Color, Font, Brushes, Image
    from System.Drawing.Imaging import ImageFormat
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    rows = int(math.ceil(len(asset_ids) / float(columns)))
    sheet = Bitmap(columns * cell, max(rows, 1) * (cell + 22))
    g = Graphics.FromImage(sheet)
    g.Clear(Color.White)
    font = Font("Segoe UI", 9)
    for i, asset_id in enumerate(asset_ids):
        thumb = os.path.join(folder, asset_id + ".png")
        x = (i % columns) * cell
        y = int(i / columns) * (cell + 22)
        try:
            if not os.path.exists(thumb):
                _client().DownloadFile("https://cdn.polyhaven.com/asset_img/thumbs/%s.png?height=%d" % (asset_id, cell), thumb)
            img = Image.FromFile(thumb)
            g.DrawImage(img, x + 4, y + 2, cell - 8, cell - 8)
            img.Dispose()
        except Exception:
            pass
        g.DrawString(asset_id, font, Brushes.Black, float(x + 4), float(y + cell - 4))
    g.Dispose()
    sheet.Save(path, ImageFormat.Png)
    sheet.Dispose()
    return path


def fetch(asset_id, folder=DEFAULT_FOLDER):
    """Downloads the glTF, its buffer and its colour textures at 1k. Skips what exists."""
    target = os.path.join(folder, asset_id)
    gltf_path = os.path.join(target, asset_id + ".gltf")
    done = {"asset": asset_id, "folder": target, "downloaded_kb": 0}
    if os.path.exists(gltf_path):
        return done
    files = _get_json(API + "/files/" + asset_id)
    entry = files["gltf"]["1k"]["gltf"]
    wanted = [(asset_id + ".gltf", entry["url"], entry.get("size", 0))]
    for rel, item in entry.get("include", {}).items():
        low = rel.lower()
        if low.endswith(".bin") or "_diff_" in low or "_col_" in low or "_color_" in low:
            wanted.append((rel, item["url"], item.get("size", 0)))
    total = 0
    for rel, url, size in wanted:
        path = os.path.join(target, rel.replace("/", os.sep))
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        _client().DownloadFile(url, path)
        total += size
    done["downloaded_kb"] = int(total / 1024)
    return done


# ---------------------------------------------------------------- glTF
_COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _accessor(gltf, buffers, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    data = buffers[view.get("buffer", 0)]
    fmt, size = _COMPONENT[acc["componentType"]]
    n = _COUNT[acc["type"]]
    stride = view.get("byteStride") or size * n
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    pack = "<" + fmt * n
    rows = []
    for i in range(acc["count"]):
        rows.append(struct.unpack_from(pack, data, start + i * stride))
    return rows


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(node):
    if "matrix" in node:
        m = node["matrix"]            # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get("translation", [0.0, 0.0, 0.0])
    qx, qy, qz, qw = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    sx, sy, sz = node.get("scale", [1.0, 1.0, 1.0])
    r = [[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
         [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
         [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0.0, 0.0, 0.0, 1.0]]


def read_parts(asset_id, folder=DEFAULT_FOLDER):
    """Returns [{material, texture, points, triangles}] in metres, Z up, front to -Y."""
    base = os.path.join(folder, asset_id)
    with open(os.path.join(base, asset_id + ".gltf"), "rb") as f:
        gltf = json.loads(f.read().decode("utf-8"))
    buffers = []
    for b in gltf.get("buffers", []):
        with open(os.path.join(base, b["uri"].replace("/", os.sep)), "rb") as f:
            buffers.append(f.read())

    def texture_of(material_index):
        try:
            mat = gltf["materials"][material_index]
            tex = mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            uri = gltf["images"][gltf["textures"][tex]["source"]]["uri"]
            return os.path.join(base, uri.replace("/", os.sep))
        except Exception:
            return None

    parts = []
    identity = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]

    def walk(node_index, parent):
        node = gltf["nodes"][node_index]
        world = _mat_mul(parent, _node_matrix(node))
        if "mesh" in node:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                raw = _accessor(gltf, buffers, prim["attributes"]["POSITION"])
                points = []
                for x, y, z in raw:
                    wx = world[0][0] * x + world[0][1] * y + world[0][2] * z + world[0][3]
                    wy = world[1][0] * x + world[1][1] * y + world[1][2] * z + world[1][3]
                    wz = world[2][0] * x + world[2][1] * y + world[2][2] * z + world[2][3]
                    points.append((wx, -wz, wy))          # glTF is Y up, Revit is Z up
                if "indices" in prim:
                    flat = [r[0] for r in _accessor(gltf, buffers, prim["indices"])]
                else:
                    flat = list(range(len(points)))
                triangles = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
                mi = prim.get("material")
                name = gltf["materials"][mi].get("name", "material") if mi is not None else "material"
                parts.append({"material": name, "texture": texture_of(mi) if mi is not None else None,
                              "points": points, "triangles": triangles})
        for child in node.get("children", []):
            walk(child, world)

    scene = gltf["scenes"][gltf.get("scene", 0)]
    for root in scene["nodes"]:
        walk(root, identity)
    return parts


def _thin(parts, limit):
    """Merges vertices on a grid until the object has at most `limit` triangles."""
    total = sum(len(p["triangles"]) for p in parts)
    if total <= limit:
        return parts, total
    xs = [pt for p in parts for pt in p["points"]]
    span = max(max(c[i] for c in xs) - min(c[i] for c in xs) for i in range(3))
    cell = span / 200.0
    while True:
        out = []
        count = 0
        for p in parts:
            keys = {}
            remap = []
            points = []
            for pt in p["points"]:
                k = (int(round(pt[0] / cell)), int(round(pt[1] / cell)), int(round(pt[2] / cell)))
                if k not in keys:
                    keys[k] = len(points)
                    points.append((k[0] * cell, k[1] * cell, k[2] * cell))
                remap.append(keys[k])
            seen = set()
            tris = []
            for a, b, c in p["triangles"]:
                a, b, c = remap[a], remap[b], remap[c]
                if a == b or b == c or a == c:
                    continue
                key = tuple(sorted((a, b, c)))
                if key in seen:
                    continue
                seen.add(key)
                tris.append((a, b, c))
            count += len(tris)
            out.append({"material": p["material"], "texture": p["texture"], "points": points, "triangles": tris})
        if count <= limit:
            return out, count
        cell *= 1.4


# ---------------------------------------------------------------- Revit
def _average_colour(path):
    try:
        import clr
        clr.AddReference("System.Drawing")
        from System.Drawing import Bitmap
        full = Bitmap(path)
        small = Bitmap(full, 8, 8)
        r = g = b = 0
        for i in range(8):
            for j in range(8):
                px = small.GetPixel(i, j)
                r += px.R
                g += px.G
                b += px.B
        small.Dispose()
        full.Dispose()
        return (int(r / 64), int(g / 64), int(b / 64))
    except Exception:
        return (150, 150, 150)


def _material(doc, name, texture):
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if m.Name == name:
            return m
    m = doc.GetElement(DB.Material.Create(doc, name))
    rgb = _average_colour(texture) if texture and os.path.exists(texture) else (150, 150, 150)
    m.Color = DB.Color(rgb[0], rgb[1], rgb[2])
    return m


def _find_type(doc, name):
    # a type's Name property is not readable from IronPython; its name parameter is
    for t in DB.FilteredElementCollector(doc).OfClass(DB.DirectShapeType):
        p = t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString() == name:
            return t
    return None


def _build_type(doc, asset_id, folder, category, max_triangles):
    name = PREFIX + asset_id
    existing = _find_type(doc, name)
    if existing is not None:
        return existing, None
    parts, count = _thin(read_parts(asset_id, folder), max_triangles)
    used = 0
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    materials = []
    geometry = List[DB.GeometryObject]()
    for part in parts:
        if not part["triangles"]:
            continue
        mat = _material(doc, PREFIX + part["material"], part["texture"])
        materials.append(mat.Name)
        # one builder per part: a built mesh carries a single material, so parts built
        # together all take the first part's material (leaves came out pot-coloured)
        builder = DB.TessellatedShapeBuilder()
        builder.OpenConnectedFaceSet(False)
        pts = [DB.XYZ(p[0] * M, p[1] * M, p[2] * M) for p in part["points"]]
        for p in part["points"]:
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
        for a, b, c in part["triangles"]:
            corners = List[DB.XYZ]()
            corners.Add(pts[a])
            corners.Add(pts[b])
            corners.Add(pts[c])
            face = DB.TessellatedFace(corners, mat.Id)
            if builder.DoesFaceHaveEnoughLoopsAndVertices(face):
                builder.AddFace(face)
                used += 1
        builder.CloseConnectedFaceSet()
        builder.Target = DB.TessellatedShapeBuilderTarget.Mesh
        builder.Fallback = DB.TessellatedShapeBuilderFallback.Salvage
        builder.Build()
        for built in builder.GetBuildResult().GetGeometricalObjects():
            geometry.Add(built)
    cat_id = DB.ElementId(category)
    if not DB.DirectShape.IsValidCategoryId(cat_id, doc):
        cat_id = DB.ElementId(DB.BuiltInCategory.OST_GenericModel)
    shape_type = DB.DirectShapeType.Create(doc, name, cat_id)
    shape_type.SetShape(geometry)
    DB.DirectShapeLibrary.GetDirectShapeLibrary(doc).AddDefinitionType(name, shape_type.Id)
    info = {"triangles": used, "size_m": [round(hi[i] - lo[i], 3) for i in range(3)],
            "base_z_m": round(lo[2], 3), "materials": sorted(set(materials))}
    return shape_type, info


def add(doc, items, folder=DEFAULT_FOLDER, max_triangles=MAX_TRIANGLES):
    """Downloads what is missing, then places every item.

    Item: asset, x, y, level, and optionally rotation (degrees), z (metres above the
    level), category ("furniture", "lighting", "plant", "generic").
    At rotation 0 an object's front faces south (-Y).
    """
    downloads = []
    for asset_id in sorted(set(i["asset"] for i in items)):
        downloads.append(fetch(asset_id, folder))

    levels = {}
    for l in DB.FilteredElementCollector(doc).OfClass(DB.Level):
        levels[l.Name] = l

    report = []
    built = {}
    t = DB.Transaction(doc, "Poly Haven objects")
    t.Start()
    try:
        for item in items:
            asset_id = item["asset"]
            category = CATEGORIES.get(item.get("category", "furniture"), DB.BuiltInCategory.OST_Furniture)
            shape_type, info = _build_type(doc, asset_id, folder, category, max_triangles)
            if info is not None:
                built[asset_id] = info
            level = levels.get(item["level"])
            if level is None:
                raise Exception(u"No level named %s" % item["level"])
            angle = item.get("rotation", 0.0) * math.pi / 180.0
            tf = DB.Transform.CreateRotation(DB.XYZ.BasisZ, angle)
            tf.Origin = DB.XYZ(item["x"] * M, item["y"] * M, level.Elevation + item.get("z", 0.0) * M)
            inst = DB.DirectShape.CreateElementInstance(doc, shape_type.Id, shape_type.Category.Id,
                                                        PREFIX + asset_id, tf)
            c = inst.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if c and not c.IsReadOnly:
                c.Set(u"Poly Haven: %s (CC0)" % asset_id)
            report.append({"asset": asset_id, "id": inst.Id.Value, "x": item["x"], "y": item["y"],
                           "rotation": item.get("rotation", 0.0)})
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return {"downloads": downloads, "built": built, "placed": report}


def purge(doc):
    """Deletes every Poly Haven instance and the built objects behind them, so the
    next `add` rebuilds them from the downloaded files. Materials stay."""
    removed = clear(doc)
    ids = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.DirectShapeType):
        p = t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and (p.AsString() or u"").startswith(PREFIX):
            ids.append(t.Id)
    if ids:
        tr = DB.Transaction(doc, "Purge Poly Haven objects")
        tr.Start()
        try:
            for i in ids:
                doc.Delete(i)
            tr.Commit()
        except Exception:
            if tr.HasStarted() and not tr.HasEnded():
                tr.RollBack()
            raise
    return {"instances": removed, "objects": len(ids)}


def clear(doc):
    """Deletes every Poly Haven instance (types and materials stay). Returns how many."""
    ids = []
    for e in DB.FilteredElementCollector(doc).OfClass(DB.DirectShape):
        p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p and (p.AsString() or u"").startswith(u"Poly Haven: "):
            ids.append(e.Id)
    if not ids:
        return 0
    t = DB.Transaction(doc, "Clear Poly Haven objects")
    t.Start()
    try:
        for i in ids:
            doc.Delete(i)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return len(ids)
