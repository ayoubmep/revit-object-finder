---
name: revit-bim-objects
description: Furnish and equip a Revit model with real BIM objects (Revit families) from a library folder - furniture, lighting, kitchen and bathroom fixtures, equipment. Finds the right family, loads it, places it at the right spot and rotation, checks the result and prepares its materials for rendering. Use when the user asks to furnish a room or a building, add furniture, lights, fixtures or equipment, use families from BIMobject, the Autodesk library or a free family site, or replace placeholder boxes with real objects.
---

# BIM objects in Revit

You furnish the model with real objects instead of modelled boxes. There are two routes, and neither needs a whole library downloaded first:

- **Fetch one object at a time** from Poly Haven's free CC0 catalogue (`scripts/polyhaven.py`). Fully automatic. Use this first.
- **Load Revit families** the user already has or downloads by hand (`scripts/bim_library.py`). Use it when a true parametric family is needed: types, schedules, manufacturer data.

## Start from a reference

When the user gives a picture, a product name or a description, find the closest object. Work in this order and stop at the first good match.

1. **Describe the reference** in a line: what it is, its shape, materials, colours and rough size. Say it back to the user, so a misread is caught early.
2. **Revit families first.** They are real BIM objects with types and data.

   ```python
   import bim_library
   result = bim_library.search(doc, ["table", "side", "round", "ronde", "gueridon"])
   ```

   It checks the families already loaded in the project, then the `.rfa` files in the library folder. Give keywords in every language the names may use. If nothing matches, tell the user which free family page comes closest and give the link; do not download it for them.
3. **Then free 3D objects.** Search Poly Haven with two or three keyword sets, tile the previews, and look at them next to the reference.

   ```python
   import polyhaven
   seen = {}
   for words in (["table", "round"], ["side", "table"], ["table", "metal"]):
       for r in polyhaven.search(words):
           seen[r["asset"]] = r
   result = polyhaven.preview_sheet(sorted(seen))       # returns the image path; open it
   ```

4. **Judge the match honestly** on four points: type, shape, material and colour, size. Compare `size_m` with the reference; a table that looks right but is twice as wide is not a match. Tell the user which it is:
   - *close*: same type, shape and materials, size within about 15 %;
   - *approximate*: right type and feel, with a named difference ("round marble top and black legs, but 1.3 m wide instead of 0.6 m");
   - *none*: say so and say what is missing. Do not place a poor substitute without asking.
5. **Place it**, then check it as below.

When the reference is a whole room, not one object:

- **Split it first** into loose objects (sofa, tables, lamps, vases, art, rug) and architecture (wall panels, stone slabs, light strips, curtains). Architecture is modelled, not searched.
- **Judge free objects on shape and size, not on colour or material.** They arrive in plain colours and you assign the appearance afterwards, so a light-wood shelf can become dark bronze. A wrong silhouette cannot be fixed.
- **Model the simple pieces yourself.** A rug, a flat TV, a picture frame or a slab-and-frame table is a few boxes with the right materials and will match the reference better than a near miss from a catalogue.
- **Expect gaps on the hero pieces.** The free catalogue is mostly vintage; a designer sofa, chandelier or floor lamp usually has no match. Say so, and tell the user what to look for as a Revit family (type, shape, width) so they can download it into the library folder.
- Give the user one table: object, best match, verdict, what you will do.

## When a piece has to be modelled

If nothing matches, model the piece, but never from bare boxes. Boxes read as toy blocks in a render however good the materials are; the final render adds light, not shape. `scripts/shapes.py` gives the forms that make a piece look made:

```python
import shapes
b = shapes.Builder(doc, floor_z=0.0, comment=u"room:living")
b.soft(fabric, 2.4, 3.2, 5.2, 4.2, 0.05, 0.36, radius=0.22, bevel=0.03)        # sofa base
b.soft(velvet, 2.5, 3.8, 3.1, 3.95, 0.51, 0.86, radius=0.06, bevel=0.05,
       tilt=("x", -14, (0, 3.95, 0.51)))                                        # cushion leaning back
b.slab(marble, 3.2, 1.55, 4.4, 2.75, 0.39, 0.43, radius=0.12)                   # table top
b.lathe(marble, 8.0, 3.9, [(0, 0.03), (0.12, 0.03), (0.07, 0.2), (0, 0.26)])    # turned lamp base
b.flutes(panel, 1.6, 6.0, 4.33, 0.0, 2.4, pitch=0.07, radius=0.03)              # ribbed wall
```

Look at the reference and go through this list for every piece:

| In the photo | Use |
|---|---|
| Upholstery: sofa bodies, arms, seat pads | `soft` with a large `radius` (0.1 to 0.25 m) and a `bevel`; one block per cushion, never one block for the whole sofa |
| Loose cushions | `soft` with `tilt`, leaning 10 to 15 degrees against the back |
| Table tops, rugs, consoles, screens | `slab` with a corner radius |
| Lamp bases, shades, vases, plinths, anything round | `lathe`, `cylinder` or `dome` |
| Ribbed or fluted panels | `flutes` (half-round ribs), not flat slats |
| Curtains | `pleats` |
| Metal frames, inlay lines, chandelier pieces | `plates`: thin bars at any angle, many of them in one element |
| A picture or patterned panel | a flat box whose material carries an image (see `appearances.py`, the `texture` setting) |

Then compare a capture with the reference and correct proportions before adding anything else: seat height near 0.4 m, sofa back near 0.75 m, coffee table near 0.4 m, legs thin (10 to 15 mm for metal). A piece that is right in proportion and soft at its edges reads as furniture; a detailed piece with wrong proportions does not.

Two traps:

- **Revit's shaded view is not the render.** A recoloured material can show black in Revit and correct in the renderer. Check the material's appearance, or the renderer, before "fixing" a colour.
- **Wide shots need a wide camera.** Revit's default perspective shows about half of what a phone photo of a room shows.

## Route 1: fetch one object at a time (Poly Haven)

Poly Haven publishes CC0 models and a public API meant for tools. Only the objects you place are downloaded, a few hundred KB each, into `C:\BIM-Library\polyhaven`.

```python
import polyhaven
result = polyhaven.search(["armchair", "modern"])       # catalogue only, nothing downloaded
```

Each hit has its `size_m` and `polycount`. Check the size against the room before choosing. Names do not tell you the style: look at the preview at `https://cdn.polyhaven.com/asset_img/thumbs/<asset>.png?height=256` before you place a period piece in a modern house.

```python
result = polyhaven.add(doc, [
    {"asset": "modern_arm_chair_01", "x": 1.15, "y": 1.5, "level": u"Niveau 1", "z": 0.02, "rotation": 90},
    {"asset": "modern_ceiling_lamp_01", "x": 3.3, "y": 1.7, "level": u"Niveau 1", "z": 2.05, "category": "lighting"},
])
```

- Metres and degrees. **At rotation 0 an object's front faces south (-Y)**; 90 turns it to face east, 180 north.
- `z` is the height above the level: the floor finish thickness for furniture, table height for an object on a table, ceiling height minus the object's height for a pendant.
- The same object placed many times is stored once and instanced.
- **Check after the first placement.** Read each instance's bounding box and look at a capture from above. Two things you cannot know in advance: which way a long object runs (a coffee table may need 90 degrees to sit parallel to the sofa), and where its origin is (a pendant lamp's origin was 0.22 m below its lowest point, so it poked through the ceiling until `z` was lowered). Correct, `clear`, and place again; the objects are already built, so the second pass is quick.
- `polyhaven.clear(doc)` removes every placed object so a layout can be redone.

### Plants, trees and garden pieces

Check how a plant's leaves are made before you fetch it. Open its `.gltf` and read each material's `alphaMode`:

- `OPAQUE`: the leaves are modelled. It works.
- `MASK` or `BLEND`: the leaves are flat cards cut out by a transparent texture. Revit drops the texture and you get rectangles. Skip it.

Garden-size trees in the catalogue are millions of triangles, so make trees from small plants that have modelled leaves:

```python
result = polyhaven.add(doc, [
    {"asset": "quiver_tree_02", "x": -8.5, "y": -1.8, "level": u"Niveau 1",
     "scale": 3.2, "split_z": 0.5, "max_triangles": 70000, "category": "plant"},
])
```

- `scale` enlarges the object when it is built. A 1.5 m aloe tree at 3.2 becomes a 4.8 m garden tree with real leaves.
- `split_z` gives everything above that fraction of the height its own material (`PH - <part>_top`), for a plant whose trunk and crown share one material.
- Several catalogue plants are a row of specimens in one object. Use the row as a planting bed or a line of young trees along a wall.
- Every placed object reports its `min_m` and `max_m`; a scaled row can be 17 m long, so read them.

Rocks, a fire pit, a gate, a statue or a bust are solid objects and come through well. Model the rest (cypresses, clipped shrubs, lavender, lamps) with turned shapes.

Know the limits and say them to the user:

- These are **geometry, not parametric families**: no types, no manufacturer data. They sit in the Furniture, Lighting or Planting category and carry the comment "Poly Haven: <id> (CC0)".
- **Revit drops a mesh's texture mapping.** Each part gets one material in the average colour of its texture, named `PH - <part>`. That average is often wrong for leaves (they came out terracotta). Give the materials a real appearance with `appearances.apply` (in this skill's `scripts`): leather, wood, a leaf texture, a glowing globe for a lamp. `appearances.VILLA_OBJECTS` is a worked example.
- **Skip trees and anything above about 60 000 triangles.** Objects over that are thinned automatically, which hurts leaves and fine detail.
- The catalogue is small and mixed in style: about 85 furniture pieces, few of them modern, no beds or sun loungers worth using. Say what is missing; do not force a poor match.
- Poly Haven asks tools using its API to credit it. Keep the comment, and tell the user where the objects came from.

## Route 2: Revit families from a folder

The library is a folder on the user's PC; you index it, load what fits, place it by code and check it.

### Where families may come from

| Source | Rule |
|---|---|
| Autodesk's Revit content library | The user installs it once from their Autodesk account (Products, Revit, Downloads, Libraries). Then it is under `C:\ProgramData\Autodesk\RVT <year>\Libraries`. |
| Free family sites, for example families.draftsperson.net | The user downloads by hand into the library folder. Do not script downloads: that site's `robots.txt` disallows automated access to its download links, and its licence forbids re-hosting the files. Give the user the page links instead. |
| Manufacturer libraries (BIMobject, BIMsmith, ARCAT) | Account required; the user downloads. Never scrape. |
| The user's own office families | Use them when asked. Do not load a client's project families into an unrelated model. |

Never put family files into a public repository unless their licence allows redistribution. Most do not. Share links.

Tell the user to keep the library outside `AppData`, for example `C:\BIM-Library`. On Windows the Claude desktop app redirects its own writes to `AppData`, so a folder created there by Claude is invisible to Revit.

### Workflow

Pass this skill's `scripts` folder as the run's `workspace`.

### 1. See what is available

```python
import bim_library
result = bim_library.index("C:/BIM-Library")
```

Match file names to what the room needs. If something is missing, say which object and where the user can get it. Do not substitute a modelled box silently.

### 2. Load

```python
import bim_library
result = bim_library.load(doc, "C:/BIM-Library/Corbu Sofa.rfa")
```

Read the answer before placing:

- `placement`: `OneLevelBased` families can be placed freely. Wall, ceiling and face based families need a host; `place` reports them instead of guessing one.
- `types`: pick the type by name; do not assume the first is the right size.
- `category`: a "sofa" filed under Generic Models still works, but schedules will not count it as furniture; tell the user.

Old families are upgraded by Revit on load. That is normal and can take a few seconds each.

### 3. Place, then check

```python
result = bim_library.place(doc, [
    {"family": "Corbu Sofa", "x": 3.7, "y": 3.0, "level": u"Niveau 1", "rotation": 180},
    {"family": "Night Stand", "x": 9.1, "y": 1.4, "level": u"Niveau 2"},
])
```

Units are metres and degrees. Every placed item comes back with its real `size_m`, `min_m` and `max_m`. Use them:

- **Size:** compare with the room. A 3.4 m sofa in a 3 m bay is wrong however good it looks.
- **Insertion point:** families are not all drawn around their centre. If `min_m`/`max_m` are not centred on your point, shift by the difference and place again. A manufacturer's corner bench, for example, was inserted by its corner: its box ran from the point to +1.486 m in x and -1.486 m in y.
- **Front:** you cannot know which way a family faces before placing it. Place once, look at it with a capture from above and from eye level, then correct `rotation`. Seats face the view or the table; beds have the head against a wall; nothing blocks a door swing.
- **Clearances:** keep 0.9 m walkways, 0.6 m around a bed, 0.75 m behind a dining chair.

`bim_library.clear(doc)` removes everything this skill placed, so a layout can be redone cleanly.

### 4. Materials

```python
result = bim_library.materials(doc, "Corbu Sofa")
```

The list can come back empty for a family built from nested components; read the materials from the nested instances, or from the Materials list by the manufacturer's prefix. Family materials often have no render appearance. For rendering, give them one with `appearances.apply`; leather, fabric, wood and metal assets exist in the Autodesk library that ships with Revit.

## What this is not for

- **Garden trees.** Free tree models are either millions of triangles or rely on transparent leaf textures, and Revit keeps neither. Revit's own tree families are render-only images. Place position markers in Revit and use the renderer's trees. Small potted plants with modelled leaves do work.
- **Objects that depend on their textures** (leaves, patterned fabric, printed surfaces). They come in as plain-coloured geometry. Import those in the renderer instead.

## Before you say it is done

- [ ] Every object is a loaded family, and you told the user where each file came from.
- [ ] Each placed object's `size_m` fits its room, and nothing overlaps a wall, a door swing or another object.
- [ ] You looked at a capture of each furnished room.
- [ ] Hosted families that were not placed are listed for the user, not dropped.
