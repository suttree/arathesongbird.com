"""Build and check the Ara test-print enclosure. All coordinates are millimetres."""

import argparse
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/ara-pot-matplotlib")
import matplotlib
matplotlib.use("Agg")
import manifold3d as md
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent


def capsule(width, height):
    """A 2D horizontal capsule with its bounding-box centre at the origin."""
    assert width > 0 and height > 0
    if height > width:
        return capsule(height, width).rotate(90)
    r = height / 2
    half = (width - height) / 2
    points = []
    for cx, start in [(half, -90), (-half, 90)]:
        for angle in np.linspace(start, start + 180, 25):
            a = math.radians(angle)
            points.append([cx + r * math.cos(a), r * math.sin(a)])
    return md.CrossSection([points])


def lathe(points, segments):
    return md.CrossSection([points]).revolve(segments)


def slot_cutter(width, height, z, angle, reach):
    return (capsule(width, height).extrude(reach)
            .rotate((90, 0, 0)).translate((0, reach, z))
            .rotate((0, 0, angle)))


def box(size, origin):
    return md.Manifold.cube(size).translate(origin)


def barrel_axis_height(p):
    return p["base_thickness"] + p["board_standoff_height"] + 6.5


# Reference coordinates from Arduino's UNO-TH_Rev3e Eagle board file, mm.
UNO_HOLES = [(66.04, 35.56), (66.04, 7.62), (15.24, 50.8), (13.97, 2.54)]
JACK_X = 8.382 - 26.67


def board_angle(p):
    """Aim the jack axis through the centre of the rear rim slot."""
    body_z = barrel_axis_height(p) - p["base_thickness"]
    radius = (p["bottom_diameter"] + (p["top_diameter"] - p["bottom_diameter"])
              * body_z / p["body_height"]) / 2
    return math.degrees(math.asin(JACK_X / radius))


def barrel_path(radius, start, length, z, angle):
    return (md.Manifold.cylinder(length, radius, circular_segments=96)
            .rotate((-90, 0, 0)).translate((JACK_X, start, z))
            .rotate((0, 0, angle)))


def make_parts(p):
    h = p["body_height"]
    rb, rt = p["bottom_diameter"] / 2, p["top_diameter"] / 2
    wall, n = p["wall"], p["segments"]
    slope = (rt - rb) / h
    inner = lambda z: rb + slope * z - wall
    seat, ledge = p["tray_seat_height"], p["tray_ledge_width"]
    bt, bh = p["base_thickness"], p["base_spigot_height"]
    slot_z = h - p["rim_strip_height"] - p["rim_slot_height"] / 2
    assert 0 < seat - ledge < seat + p["tray_height"] < slot_z - p["rim_slot_height"] / 2
    body = lathe([(rb, 0), (rt, h), (inner(h), h),
                  (inner(seat), seat), (inner(seat) - ledge, seat),
                  (inner(seat - ledge), seat - ledge), (inner(0), 0)], n)
    reach = rt + 18
    for rim_angle in [0, 90, 180, 270]:
        body -= slot_cutter(p["rim_slot_width"], p["rim_slot_height"], slot_z, rim_angle, reach)

    # Keep the round opening above the base disk and its locating ring.
    board_z = bt + p["board_standoff_height"]
    angle = board_angle(p)
    port_z = barrel_axis_height(p)
    port_radius = p["power_opening_diameter"] / 2
    assert port_z - port_radius > bt + bh
    body -= barrel_path(port_radius, 0, reach, port_z - bt, angle)

    r0 = inner(seat) - p["tray_radial_clearance"]
    th, tf, tw = p["tray_height"], p["tray_floor"], p["tray_wall"]
    rtop = r0 + slope * th
    tray = lathe([(0, 0), (r0, 0), (rtop, th), (rtop - tw, th),
                  (r0 + slope * tf - tw, tf), (0, tf)], n)
    # The speaker faces upward through the tray rather than into the PCB.
    sw, sl, sd = (p[k] for k in ("speaker_width", "speaker_length", "speaker_depth"))
    for i, trim in enumerate([18, 12, 10, 12, 18], -2):
        tray -= capsule(sw - trim, 2.6).extrude(th + 2).translate((0, i * sl / 8, -1))

    ro = inner(0) - p["base_radial_clearance"]
    ri = ro - p["base_spigot_wall"]
    base = lathe([(0, 0), (rb, 0), (rb, bt), (ro, bt),
                  (ro, bt + bh - 0.6), (ro - 0.6, bt + bh),
                  (ri, bt + bh), (ri, bt), (0, bt)], n)
    edge = p["board_front_edge_y"]
    for bx, by in UNO_HOLES:
        x, y = by - 26.67, edge - bx
        boss = md.Manifold.cylinder(p["board_standoff_height"] + 0.4, 3.0, circular_segments=48)
        base += boss.translate((x, y, bt - 0.4)).rotate((0, 0, angle))
        pilot = md.Manifold.cylinder(5.5, 1.05, circular_segments=32)
        base -= pilot.translate((x, y, board_z - 5.0)).rotate((0, 0, angle))

    def wedge(low, high, start, angle):
        return md.CrossSection([[(0, low), (reach, low), (reach, high), (0, high)]]
                               ).revolve(96, angle).rotate((0, 0, start))

    rim_test = (body ^ wedge(h - 18, h + 1, 55, 70)).translate((0, 0, 18 - h))
    rear_test = body ^ wedge(0, 29, 45, 90)
    parts = {"body": body, "inner_tray": tray, "base_cover": base,
             "rim_clip_test": rim_test, "rear_port_test": rear_test}

    # Deliberately oversized electronics envelopes, not printed components.
    board = box((57, 74, 31), (-28.5, edge - 71.5, board_z))
    # Leave room around the speaker housing for mounting tape and tolerance.
    speaker = box((sw + 2, sl + 2, sd + 3),
                  (-(sw + 2)/2, -(sl + 2)/2, bt + seat - 1 - (sd + 3)))
    rtc = box((34, 11, 26), (-17, -48, 8))
    hardware = {"uno_with_jumpers": board.rotate((0, 0, angle)),
                "speaker_reserve": speaker, "rtc_reserve": rtc.rotate((0, 0, angle))}
    return parts, hardware, inner, slot_z


def to_trimesh(solid):
    assert solid.status() == md.Error.NoError, str(solid.status())
    raw = solid.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(raw.vert_properties)[:, :3],
                           faces=np.asarray(raw.tri_verts), process=True)


def component_count(mesh):
    """Count vertex-connected components of the reloaded STL without a graph add-on."""
    parents = list(range(len(mesh.vertices)))

    def root(a):
        while parents[a] != a:
            parents[a] = parents[parents[a]]
            a = parents[a]
        return a

    for a, b, c in mesh.faces:
        ra = root(int(a))
        parents[root(int(b))] = ra
        parents[root(int(c))] = ra
    return len({root(i) for i in range(len(parents))})


def render_panel(items, size, azimuth, elevation):
    """Orthographic triangle rasterizer with a depth buffer for concave meshes."""
    from PIL import Image
    meshes = []
    for solid, color, offset in items:
        mesh = to_trimesh(solid)
        meshes.append((mesh.vertices + np.asarray(offset), mesh.faces,
                       mesh.face_normals, np.asarray(color)))
    az, el = np.radians([azimuth, elevation])
    view = np.array([math.cos(az) * math.cos(el),
                     math.sin(az) * math.cos(el), math.sin(el)])
    right = np.array([-math.sin(az), math.cos(az), 0])
    up = np.cross(view, right)
    basis = np.stack([right, -up, view], axis=1)
    projected = [v @ basis for v, _, _, _ in meshes]
    all_xy = np.vstack(projected)[:, :2]
    lo, hi = all_xy.min(axis=0), all_xy.max(axis=0)
    width, height = size
    scale = min((width - 50) / (hi[0] - lo[0]),
                (height - 40) / (hi[1] - lo[1]))
    centre = (lo + hi) / 2
    pixels = np.full((height, width, 3), [246, 240, 233], dtype=np.uint8)
    depth = np.full((height, width), -np.inf)
    light = np.array([-0.4, -0.7, 0.8])
    light /= np.linalg.norm(light)
    for coordinates, (_, faces, normals, color) in zip(projected, meshes):
        coordinates[:, :2] = ((coordinates[:, :2] - centre) * scale
                              + [width / 2, height / 2])
        shades = np.clip(0.55 + 0.45 * (normals @ light), 0.28, 1)
        for face, shade in zip(faces, shades):
            triangle = coordinates[face]
            x0, y0, z0 = triangle[0]
            x1, y1, z1 = triangle[1]
            x2, y2, z2 = triangle[2]
            denom = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
            if abs(denom) < 1e-10:
                continue
            low = np.maximum(np.floor(triangle[:, :2].min(axis=0)), [0, 0]).astype(int)
            high = np.minimum(np.ceil(triangle[:, :2].max(axis=0)),
                              [width-1, height-1]).astype(int)
            if np.any(high < low):
                continue
            xs = np.arange(low[0], high[0]+1)[None, :] + 0.5
            ys = np.arange(low[1], high[1]+1)[:, None] + 0.5
            a = ((y1-y2)*(xs-x2) + (x2-x1)*(ys-y2)) / denom
            b = ((y2-y0)*(xs-x2) + (x0-x2)*(ys-y2)) / denom
            c = 1-a-b
            z = a*z0 + b*z1 + c*z2
            region = (slice(low[1], high[1]+1), slice(low[0], high[0]+1))
            mask = (a >= -1e-8) & (b >= -1e-8) & (c >= -1e-8) & (z > depth[region])
            depth[region][mask] = z[mask]
            pixels[region][mask] = np.clip(color * shade * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def preview(parts, hardware, p, out):
    from PIL import Image, ImageDraw, ImageFont
    fonts = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    font = lambda size: ImageFont.truetype(str(fonts / "DejaVuSans.ttf"), size)
    canvas = Image.new("RGB", (1800, 1380), (246, 240, 233))
    labels = ImageDraw.Draw(canvas)
    ink = "#29231e"
    labels.text((50, 32), "Ara / UNO R3 fit-test v5", fill=ink, font=font(34))
    clay, pale, pcb, speaker, rtc = (.83, .38, .21), (.83, .73, .60), (.19, .58, .40), (.30, .36, .44), (.52, .55, .20)
    zero = (0, 0, 0)
    bt, seat = p["base_thickness"], p["tray_seat_height"]
    body = (parts["body"], clay, (0, 0, bt))
    tray = (parts["inner_tray"], pale, (0, 0, bt + seat))
    base = (parts["base_cover"], clay, zero)
    components = [(hardware["uno_with_jumpers"], pcb, zero),
                  (hardware["speaker_reserve"], speaker, zero),
                  (hardware["rtc_reserve"], rtc, zero)]
    half = box((180, 90, 150), (-90, 0, -10))
    section = [(solid ^ half, color, position) for solid, color, position in [body, tray, base]]
    panels = [
        ("Front / four clip slots and speaker grille", [body, tray, base], -62, 35),
        (f"Rear / {p['power_opening_diameter']:g} mm centred power bore", [body, tray, base], 90, 12),
        ("Cutaway / electronics clearance envelopes", section + components, -64, 19),
        ("First fit check / base and short rear wall", [(parts["rear_port_test"], clay, (0, 0, bt)), base, components[0]], 69, 36),
    ]
    for i, (title, items, az, el) in enumerate(panels):
        x, y = 50 + (i % 2) * 875, 100 + (i // 2) * 585
        labels.text((x, y), title, fill=ink, font=font(23))
        canvas.paste(render_panel(items, (825, 520), az, el), (x, y + 35))
    labels.text((50, 1305), f"Rim {p['top_diameter']:g} mm · base {p['bottom_diameter']:g} mm · assembled height {p['body_height'] + bt:g} mm", fill=ink, font=font(20))
    labels.text((50, 1340), "Green: UNO and jumpers. Blue-grey: speaker. Olive: RTC. Blocks show reserved space, not exact component shapes.", fill=ink, font=font(17))
    canvas.save(out / "preview.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parameters", type=Path, default=HERE / "parameters.json")
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    p = json.loads(args.parameters.read_text())
    parts, hardware, inner, slot_z = make_parts(p)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"units": "mm", "prototype_only": True, "parts": {}}
    for name, solid in parts.items():
        mesh = to_trimesh(solid)
        target = args.output / (name + ".stl")
        mesh.export(target)
        loaded = trimesh.load_mesh(target, process=True)
        assert loaded.is_watertight and loaded.is_winding_consistent and loaded.is_volume, name
        assert component_count(loaded) == 1, name
        assert abs(float(loaded.bounds[0, 2])) < 1e-4, name
        report["parts"][name] = {"watertight": True, "connected_components": 1,
                                 "size_mm": loaded.extents.round(3).tolist(),
                                 "volume_mm3": round(float(loaded.volume), 2)}
    assert len(parts["body"].slice(slot_z).decompose()) == 4
    grille_section = parts["inner_tray"].slice(p["tray_floor"] / 2)
    assert grille_section.num_contour() == 6  # Outer edge and five grille slots.
    bt = p["base_thickness"]
    seat = p["tray_seat_height"]
    assembled = [parts["body"].translate((0, 0, bt)),
                 parts["inner_tray"].translate((0, 0, bt + seat)), parts["base_cover"]]
    # Check the plug path along the jack axis through the assembled enclosure.
    edge = p["board_front_edge_y"]
    angle = board_angle(p)
    plug_checks = {
        "barrel_11_mm": barrel_path(5.5, edge + 1.8, 35, barrel_axis_height(p), angle),
    }
    for i, solid in enumerate(assembled):
        for j, other in enumerate(assembled[:i]):
            assert (solid ^ other).volume() < 1e-5, ("printed parts overlap", i, j)
        for name, space in (hardware | plug_checks).items():
            assert (solid ^ space).volume() < 1e-5, ("clearance collision", i, name)
    for i, (name, solid) in enumerate(hardware.items()):
        for other_name, other in list(hardware.items())[:i]:
            assert (solid ^ other).volume() < 1e-5, (name, other_name)
    min_open = inner(0) * math.cos(math.pi / p["segments"])
    # The shell can be lowered over the flat UNO envelope without tilting it.
    board_radius = np.linalg.norm(to_trimesh(hardware["uno_with_jumpers"]).vertices[:, :2], axis=1).max()
    assert board_radius < min_open
    assert (assembled[0] ^ assembled[1].translate((0, 0, -0.5))).volume() > 0
    report["fit_checks"] = {
        "rim_openings": 4,
        "speaker_grille_openings": grille_section.num_contour() - 1,
        "power_opening_diameter_mm": p["power_opening_diameter"],
        "power_bore_angle_from_radial_deg": round(abs(angle), 2),
        "assembled_height_mm": p["body_height"] + bt,
        "minimum_opening_diameter_mm": round(2 * min_open, 3),
        "board_insertion_radial_margin_mm": round(float(min_open - board_radius), 3),
        "assembled_envelope_bounds_mm": {
            name: to_trimesh(solid).bounds.round(2).tolist() for name, solid in hardware.items()
        },
        "unobstructed_plug_envelopes": list(plug_checks),
        "printed_parts_and_hardware_clearance_passed": True,
        "physical_fit_verified": False,
    }
    (args.output / "mesh-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    preview(parts, hardware, p, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
