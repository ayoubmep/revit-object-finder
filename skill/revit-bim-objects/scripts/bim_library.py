# -*- coding: utf-8 -*-
"""Load Revit families from a folder and place them by code.

The folder is the library: anything the user has the right to use goes in it
(Autodesk's content library, manufacturer downloads, free family sites).

    import bim_library
    files = bim_library.index("C:/BIM-Library")                   # what is available
    info = bim_library.load(doc, files[0]["path"])                # outside a transaction
    report = bim_library.place(doc, [
        {"family": "Corbu Sofa", "x": 3.7, "y": 3.0, "level": u"Niveau 1", "rotation": 180},
    ])

Coordinates are in metres, rotation in degrees counter-clockwise seen from above.
`place` returns each instance's real size and position, so the result can be checked
and corrected: a family's own "front" is not known until it has been placed once.
"""
import math
import os
try:
    from pyrevit.api import DB, UI
except ImportError:      # any other bridge that runs Python inside Revit
    import clr
    clr.AddReference('RevitAPI')
    clr.AddReference('RevitAPIUI')
    from Autodesk.Revit import DB, UI

M = 1.0 / 0.3048
DEFAULT_FOLDER = "C:\\BIM-Library"
TAG = u"bim:library"


class _LoadOptions(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = False
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        overwriteParameterValues.Value = False
        return True


def index(folder=DEFAULT_FOLDER):
    """Every .rfa under the folder, without Revit's numbered backups (name.0001.rfa)."""
    found = []
    if not os.path.isdir(folder):
        return found
    for root, _dirs, names in os.walk(folder):
        for name in sorted(names):
            low = name.lower()
            if not low.endswith(".rfa"):
                continue
            stem = name[:-4]
            tail = stem.rsplit(".", 1)[-1]
            if "." in stem and len(tail) == 4 and tail.isdigit():
                continue
            path = os.path.join(root, name)
            found.append({"name": stem, "path": path,
                          "folder": os.path.relpath(root, folder),
                          "kb": int(os.path.getsize(path) / 1024)})
    return found


def search(doc, words, folder=DEFAULT_FOLDER):
    """Revit families that match a reference, best first.

    Looks at the families already loaded in the project, then at the .rfa files in the
    library folder. `words` are keywords for the object, in every language the family
    names may use (a French project needs "canape" as well as "sofa"). A family scores
    one point per word found in its name or category.
    """
    words = [w.lower() for w in words]

    def score(text):
        low = text.lower()
        return sum(1 for w in words if w in low)

    loaded = []
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        category = f.FamilyCategory.Name if f.FamilyCategory else u""
        s = score(f.Name + u" " + category)
        if s:
            loaded.append({"family": f.Name, "category": category, "score": s,
                           "placement": str(f.FamilyPlacementType)})
    files = []
    for item in index(folder):
        s = score(item["name"] + " " + item["folder"])
        if s:
            row = dict(item)
            row["score"] = s
            files.append(row)
    loaded.sort(key=lambda r: -r["score"])
    files.sort(key=lambda r: -r["score"])
    return {"loaded": loaded[:20], "files": files[:20]}


def find_family(doc, name):
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        if f.Name == name:
            return f
    return None


def _symbols(doc, family):
    return [doc.GetElement(i) for i in family.GetFamilySymbolIds()]


def _type_name(symbol):
    p = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    return p.AsString() if p else symbol.Name


def describe(doc, family):
    return {"family": family.Name,
            "category": family.FamilyCategory.Name if family.FamilyCategory else None,
            "placement": str(family.FamilyPlacementType),
            "types": [_type_name(s) for s in _symbols(doc, family)]}


def load(doc, path):
    """Loads one family file. Call it outside a transaction. Returns what was loaded."""
    name = os.path.basename(path)[:-4]
    family = find_family(doc, name)
    loaded = False
    if family is None:
        import clr
        ref = clr.Reference[DB.Family]()
        t = DB.Transaction(doc, "Load family " + name)
        t.Start()
        try:
            loaded = doc.LoadFamily(path, _LoadOptions(), ref)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
        family = ref.Value if loaded else find_family(doc, name)
    if family is None:
        return {"family": name, "loaded": False, "reason": "Revit refused the file"}
    out = describe(doc, family)
    out["loaded"] = loaded
    return out


def _level(doc, name):
    for l in DB.FilteredElementCollector(doc).OfClass(DB.Level):
        if l.Name == name:
            return l
    raise Exception(u"No level named %s" % name)


def _pick_symbol(doc, family, type_name):
    symbols = _symbols(doc, family)
    if not symbols:
        raise Exception(u"Family %s has no types" % family.Name)
    if type_name:
        for s in symbols:
            if _type_name(s) == type_name:
                return s
        raise Exception(u"Family %s has no type %s. Types: %s" % (
            family.Name, type_name, u", ".join(_type_name(s) for s in symbols)))
    return symbols[0]


def _box(element):
    bb = element.get_BoundingBox(None)
    if bb is None:
        return None
    return {"size_m": [round((bb.Max.X - bb.Min.X) / M, 3), round((bb.Max.Y - bb.Min.Y) / M, 3),
                       round((bb.Max.Z - bb.Min.Z) / M, 3)],
            "min_m": [round(bb.Min.X / M, 3), round(bb.Min.Y / M, 3), round(bb.Min.Z / M, 3)],
            "max_m": [round(bb.Max.X / M, 3), round(bb.Max.Y / M, 3), round(bb.Max.Z / M, 3)]}


def place(doc, items, comment=TAG):
    """Places level-based families. Each item: family, x, y, level, and optionally
    type, rotation (degrees), z (metres above the level), mirror (True/False).

    Families that need a host (wall, ceiling, face) are reported, not placed.
    """
    report = []
    t = DB.Transaction(doc, "Place library families")
    t.Start()
    try:
        for item in items:
            row = {"family": item["family"]}
            family = find_family(doc, item["family"])
            if family is None:
                row["placed"] = False
                row["reason"] = "not loaded"
                report.append(row)
                continue
            kind = str(family.FamilyPlacementType)
            if kind not in ("OneLevelBased", "TwoLevelsBased", "WorkPlaneBased"):
                row["placed"] = False
                row["reason"] = "needs a host: " + kind
                report.append(row)
                continue
            symbol = _pick_symbol(doc, family, item.get("type"))
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            level = _level(doc, item["level"])
            z = level.Elevation + item.get("z", 0.0) * M
            point = DB.XYZ(item["x"] * M, item["y"] * M, z)
            inst = doc.Create.NewFamilyInstance(point, symbol, level, DB.Structure.StructuralType.NonStructural)
            if item.get("z"):
                p = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
                if p is None or p.IsReadOnly:
                    p = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM)
                if p is not None and not p.IsReadOnly:
                    p.Set(item["z"] * M)
            angle = item.get("rotation", 0.0)
            if angle:
                axis = DB.Line.CreateBound(point, point + DB.XYZ.BasisZ)
                DB.ElementTransformUtils.RotateElement(doc, inst.Id, axis, angle * math.pi / 180.0)
            c = inst.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if c and not c.IsReadOnly:
                c.Set(comment)
            doc.Regenerate()
            row["placed"] = True
            row["id"] = inst.Id.Value
            row["type"] = _type_name(symbol)
            row["category"] = family.FamilyCategory.Name if family.FamilyCategory else None
            box = _box(inst)
            if box:
                row.update(box)
            report.append(row)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return report


def clear(doc, comment=TAG):
    """Deletes every instance placed with this comment. Returns how many."""
    ids = []
    for e in DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance):
        p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p and p.AsString() == comment:
            ids.append(e.Id)
    if not ids:
        return 0
    t = DB.Transaction(doc, "Clear library families")
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


def materials(doc, family_name):
    """Names of the materials used by the placed instances of a family, so they can be
    given render appearances (see appearances.py)."""
    names = set()
    for e in DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance):
        if e.Symbol.Family.Name != family_name:
            continue
        for mid in e.GetMaterialIds(False):
            m = doc.GetElement(mid)
            if m is not None:
                names.add(m.Name)
    return sorted(names)
