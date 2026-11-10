# Real objects in Revit, found and placed by Claude

A Claude skill that furnishes a Revit model with real objects instead of modelled boxes. You describe what you want, or show a reference, and Claude finds the closest object, downloads only that one, places it at the right spot and rotation, and checks the result.

> Furnish the living room: two armchairs, a coffee table, a sideboard and a pendant light.

> Find something close to this chair and put two of them facing the window.

No library has to be downloaded first. This project is not affiliated with Autodesk or Poly Haven and contains no model or family files.

## How it finds an object

1. **Revit families first.** Claude searches the families already in your project and the `.rfa` files in your library folder (for example `C:\BIM-Library`). Families are real BIM objects, with types and data.
2. **Then free 3D objects.** If no family fits, Claude searches [Poly Haven](https://polyhaven.com), a public-domain (CC0) catalogue with a public API. It tiles the preview pictures, compares them with your reference by eye, checks the size, and tells you how close the match is: close, approximate (with the difference named), or none.
3. **One object at a time.** Only what is placed is downloaded, a few hundred KB to 2 MB each, into `C:\BIM-Library\polyhaven`.
4. **If nothing fits, it is modelled, and not from boxes.** A shapes module gives rounded corners, softened upholstery edges, turned forms for lamps and vases, leaning cushions, half-round ribs and pleats, so a modelled sofa reads as a sofa and not as stacked blocks.

## What you get, and what you do not

| | Revit family | Poly Haven object |
|---|---|---|
| Geometry | Parametric | Fixed mesh |
| Types, schedules, manufacturer data | Yes | No |
| Category | The family's own | Furniture, Lighting or Planting |
| Materials | The family's own | One plain colour per part, taken from its texture |
| Download | You, by hand | Claude, automatically |

Two limits to know before you rely on it:

- **Revit cannot keep a mesh's texture mapping.** Objects arrive in plain colours. The skill can then give each part a real render appearance (leather, wood, fabric, a glowing lamp globe) from the Autodesk material library that ships with Revit.
- **Trees need a trick.** Free garden-size trees are millions of triangles or rely on transparent leaf textures, which Revit cannot keep. The skill instead takes a small plant with modelled leaves and enlarges it: a 1.5 m aloe tree becomes a 4.8 m garden tree. It checks each plant first and skips the ones that would come out as flat cards. Your renderer's own trees are still better.

The Poly Haven catalogue is small and mixed in style: about 85 furniture pieces, many of them vintage. Claude will say when nothing fits rather than place a poor match.

## Requirements

- Windows, Revit, and [pyRevit](https://github.com/pyrevitlabs/pyRevit) with a Claude connection that can run Python inside Revit.
- Internet access from Revit, for the Poly Haven route.

## Install

The skill is the folder `skill/revit-bim-objects`.

- **Claude Code:** copy that folder to `~/.claude/skills/`.
- **Claude desktop app:** zip the folder and add it under Settings, Capabilities, Skills.

## Where families may come from

The skill never downloads Revit families for you. Put files you are allowed to use in your library folder:

- Autodesk's Revit content library, from your Autodesk account.
- Free sites such as <https://families.draftsperson.net/>. Download by hand: that site does not allow automated downloads or re-hosting of its files.
- Manufacturer libraries such as BIMobject, with your own account.

## Files

| File | What it does |
|---|---|
| `SKILL.md` | The instructions Claude follows, including how to match a reference. |
| `scripts/polyhaven.py` | Search the catalogue, tile previews, fetch one object, build it in Revit, place it. |
| `scripts/bim_library.py` | Search, load and place Revit families from the project and a folder; report each placed object's real size. |
| `scripts/shapes.py` | Model a missing piece with rounded, soft, turned and tilted forms instead of boxes. |
| `scripts/garden.py` | Turned forms for the garden and street: cypresses, garden lights, a parasol, stools, street lamps. |
| `scripts/appearances.py` | Give materials a render appearance from the Autodesk library, recolour one, or put an image on a surface. |

## Credit

Objects fetched by this skill come from [Poly Haven](https://polyhaven.com) and are CC0. Each placed object carries the comment "Poly Haven: <id> (CC0)". If you publish work made with it, a mention of Poly Haven is appreciated by its authors.

## Test status

Tested on one PC: Revit 2026, pyRevit 7.

- Poly Haven route: nine different objects, eighteen placements, 8.6 MB downloaded, then corrected for rotation and height.
- Reference lookup: run on a single-object description and on a photo of a furnished living room (ten objects searched, 50 previews compared).
- Family-folder route: indexed, loaded and placed a manufacturer family from BIMobject in a dry run; it came in at its stated size.
- Garden: three enlarged aloe trees, two rows of young trees, rock groups, a fire pit, an iron gate and two sculptures fetched and placed (25 objects in all, about 24 MB).
- Modelling from a photo: a living room rebuilt from a reference picture with the shapes module (sofas, cushions, ribbed wall, marble and brass table, leaf chandelier, turned floor lamp).
