# -*- coding: utf-8 -*-
"""Give Revit materials real render appearances so a renderer receives finished materials.

D5 Live Sync converts each Revit material's *appearance asset* (the Appearance tab),
not its shading colour. It understands Autodesk's standard asset types, so a material
whose appearance is an Autodesk "Water" asset arrives in D5 as water, a textured wood
arrives with its texture, and a self-illuminated one arrives as a light-emitting
material. Nothing has to be re-assigned in D5.

    import appearances
    result = appearances.apply(doc, appearances.VILLA)

The mapping is {Revit material name: library asset name}, or
{Revit material name: (library asset name, {property: value})} to adjust a copy of the
asset: a number sets a number, an (r, g, b) tuple sets a colour and removes its texture.

Asset names are the library's internal ids and are the same in every Revit language.
To find others, list `app.GetAssets(DB.Visual.AssetType.Appearance)` and read each
asset's "BaseSchema" and the file name of its connected "unifiedbitmap_Bitmap".
"""
try:
    from pyrevit.api import DB, UI
except ImportError:      # any other bridge that runs Python inside Revit
    import clr
    clr.AddReference('RevitAPI')
    clr.AddReference('RevitAPIUI')
    from Autodesk.Revit import DB, UI

# Revit material -> Autodesk appearance library asset
VILLA = {
    u"Demo - Eau": u"Water-001",                 # Water schema, swimming pool
    u"Demo - Pelouse": u"Generic-021",           # Sitework.Planting.Grass.Thick
    u"Demo - Bardage bois": u"ACADGen-365",      # Siding Panels.Wood.Horizontal.Cedar
    u"Demo - Lames bois": u"ACADGen-394",        # Finish Carpentry.Wood.Teak
    u"Demo - Terrasse bois": u"ACADGen-106",     # Flooring.Wood.Plank
    u"Demo - Enduit blanc": u"ACADGen-154",      # Plaster.Stucco.Fine.White
    u"Demo - Beton": u"ACADGen-007",             # Concrete.Cast-In-Place.Flat.Grey.2
    u"Demo - Pierre": u"ACADGen-271",            # Masonry.Stone.Limestone.Ashlar.Coursed
    u"Demo - Carrelage piscine": u"Ceramic-032",  # Tiling.Ceramic.Mosaic.Blue
    u"Demo - Paves": u"ACADGen-331",             # Paving - Surfacing.Pavers.Square
    u"Demo - Gravier": u"Generic-020",           # Planting.Gravel.Mixed
    u"Demo - Haie": u"Generic-023",              # hedge
    u"Demo - Feuillage": u"Generic-023",         # hedge (placeholder trees)
    u"Demo - Tronc": u"ACADGen-395",             # Finish Carpentry.Wood.Walnut
    u"Demo - Parquet": u"ACADGen-397",           # Finish Carpentry.Wood.White Oak
    u"Demo - Tissu clair": u"ACADGen-190",       # Fabrics.Linen.White
    u"Demo - Marbre": u"ACADGen-084",            # Flooring.Marble.White
    u"Demo - Tissu sofa": u"ACADGen-188",        # Fabrics.Linen.Beige
    u"Demo - Tapis": u"ACADGen-189",             # Fabrics.Linen.Tweed
    u"Demo - Laiton": u"Metal-013",              # Metal schema, brass
    u"Demo - Cannelures": (u"Paint-056", {"wallpaint_color": (206, 199, 189)}),
    u"Demo - Velours brun": (u"Paint-056", {"wallpaint_color": (122, 82, 56)}),
    # a paint asset recoloured to near black, for frames and the pergola
    u"Demo - Metal sombre": (u"Paint-056", {"wallpaint_color": (38, 38, 40)}),
    # a self-illuminated generic asset: arrives in D5 as an emissive material
    u"Demo - LED": (u"Generic-022", {"generic_diffuse": (255, 236, 205),
                                     "generic_self_illum_luminance": 2500.0,
                                     "generic_self_illum_color_temperature": 3000.0}),
}

# Appearances for the Poly Haven objects used in the demo villa (revit-bim-objects skill).
# Those objects arrive in plain colours; this gives them leather, wood and leaf textures.
VILLA_OBJECTS = {
    u"PH - modern_arm_chair_01_pillow": u"ACADGen-182",      # Fabrics.Leather.Black
    u"PH - modern_arm_chair_01_legs": u"ACADGen-395",        # Wood.Walnut
    u"PH - mid_century_lounge_chair": u"ACADGen-184",        # Fabrics.Leather.Brown
    u"PH - dining_chair_02": u"ACADGen-184",
    u"PH - modern_coffee_table_01": u"ACADGen-397",          # Wood.White Oak
    u"PH - modern_wooden_cabinet": u"ACADGen-395",
    u"PH - outdoor_table_chair_set_01_chair": u"ACADGen-394",  # Wood.Teak
    u"PH - outdoor_table_chair_set_01_table": u"ACADGen-394",
    u"PH - potted_plant_02_leaves": u"Generic-023",          # hedge
    u"PH - potted_plant_04": u"Generic-023",
    u"PH - potted_plant_02_pot": (u"Paint-056", {"wallpaint_color": (168, 96, 62)}),
    u"PH - ceramic_vase_01": (u"Paint-056", {"wallpaint_color": (238, 236, 230)}),
    u"PH - ceramic_vase_04": (u"Paint-056", {"wallpaint_color": (238, 236, 230)}),
    u"PH - brass_vase_03": u"Metal-013",                     # Metal schema, brass
    u"PH - brass_vase_04": u"Metal-013",
    u"PH - wooden_candlestick": u"ACADGen-395",
    u"PH - modern_ceiling_lamp_01": (u"Paint-056", {"wallpaint_color": (236, 236, 232)}),
    u"PH - modern_ceiling_globe": (u"Generic-022", {"generic_diffuse": (255, 240, 215),
                                                    "generic_self_illum_luminance": 2500.0,
                                                    "generic_self_illum_color_temperature": 3000.0}),
}

PREFIX = u"BIM - "


def _library(doc, wanted):
    found = {}
    for asset in doc.Application.GetAssets(DB.Visual.AssetType.Appearance):
        name = asset.Name
        if name in wanted and name not in found:
            found[name] = asset
            if len(found) == len(wanted):
                break
    return found


def _tune(doc, element, tweaks):
    """Edit a document appearance asset in place. Returns the property names not found."""
    problems = []
    scope = DB.Visual.AppearanceAssetEditScope(doc)
    try:
        asset = scope.Start(element.Id)
        for key in sorted(tweaks):
            value = tweaks[key]
            prop = asset.FindByName(key)
            if prop is None:
                problems.append(key)
                continue
            try:
                if isinstance(value, tuple):
                    if prop.NumberOfConnectedProperties > 0:
                        prop.RemoveConnectedAsset()
                    prop.SetValueAsColor(DB.Color(value[0], value[1], value[2]))
                else:
                    try:
                        prop.Value = float(value)
                    except Exception:
                        prop.Value = int(value)
            except Exception:
                problems.append(key)
        scope.Commit(True)
    finally:
        scope.Dispose()
    return problems


def apply(doc, mapping):
    materials = {}
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        materials[m.Name] = m
    plan = {}
    for mat_name, spec in mapping.items():
        if isinstance(spec, tuple):
            plan[mat_name] = (spec[0], spec[1])
        else:
            plan[mat_name] = (spec, None)
    missing_materials = sorted(n for n in plan if n not in materials)
    wanted = set(a for a, _ in plan.values())
    library = _library(doc, wanted)
    missing_assets = sorted(wanted - set(library))

    done = []
    not_tuned = {}
    t = DB.Transaction(doc, "D5 material appearances")
    t.Start()
    try:
        for mat_name in sorted(plan):
            asset_name, tweaks = plan[mat_name]
            if mat_name not in materials or asset_name not in library:
                continue
            # a tuned asset is private to its material; a plain one is shared
            element_name = PREFIX + (mat_name if tweaks else asset_name)
            element = DB.AppearanceAssetElement.GetAppearanceAssetElementByName(doc, element_name)
            if element is None:
                element = DB.AppearanceAssetElement.Create(doc, element_name, library[asset_name])
            if tweaks:
                problems = _tune(doc, element, tweaks)
                if problems:
                    not_tuned[mat_name] = problems
            material = materials[mat_name]
            material.AppearanceAssetId = element.Id
            material.UseRenderAppearanceForShading = True
            done.append(mat_name)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return {"assigned": done, "missing_materials": missing_materials,
            "missing_library_assets": missing_assets, "properties_not_set": not_tuned}
