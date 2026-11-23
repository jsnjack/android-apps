#!/usr/bin/env python3
"""Turns the apps' Android launcher icons into SVG files for the install page.

Each app's icon is an Android vector drawable, or an adaptive icon made of a
background and a foreground drawable. The converter handles what those use:
paths with fill, alpha and stroke, groups with translate/scale/rotate, and
linear and radial gradients. An adaptive icon shows its middle 72 of 108 units.

Run `make icons` after an app changes its icon.
"""

import pathlib
import sys
import xml.etree.ElementTree as ET

A = "{http://schemas.android.com/apk/res/android}"
WORKSPACE = pathlib.Path(__file__).resolve().parent.parent

# App: (resource directory, icon reference from the manifest).
APPS = {
    "desklink": ("desklink/android/app/src/main/res", "@drawable/ic_launcher"),
    "wallet": ("wallet/app/src/main/res", "@mipmap/ic_launcher"),
    "weather-widget": ("weather/android/app/src/main/res", "@drawable/ic_widget_preview"),
    "wahoo-share": ("wahoo-share/app/src/main/res", "@mipmap/ic_launcher"),
}


def resolve(res, ref):
    kind, name = ref.lstrip("@").split("/")
    for d in sorted(res.glob(kind + "*")):
        f = d / (name + ".xml")
        if f.is_file():
            return f
    raise FileNotFoundError(f"{ref} in {res}")


def colour(value):
    """#AARRGGBB or #RRGGBB to (#RRGGBB, opacity)."""
    v = value.lstrip("#")
    if len(v) == 8:
        return "#" + v[2:], int(v[:2], 16) / 255
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return "#" + v, 1.0


class Converter:
    def __init__(self, prefix):
        self.prefix = prefix
        self.defs = []
        self.count = 0

    def gradient(self, g):
        self.count += 1
        gid = f"{self.prefix}g{self.count}"
        stops = []
        items = g.findall("item")
        if items:
            for it in items:
                c, o = colour(it.get(A + "color"))
                stops.append((float(it.get(A + "offset")), c, o))
        else:
            for off, key in ((0, "startColor"), (0.5, "centerColor"), (1, "endColor")):
                if g.get(A + key):
                    c, o = colour(g.get(A + key))
                    stops.append((off, c, o))
        stop_xml = "".join(f'<stop offset="{off}" stop-color="{c}" stop-opacity="{o:.3f}"/>' for off, c, o in stops)
        if g.get(A + "type") == "radial":
            self.defs.append(
                f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="{g.get(A + "centerX")}" '
                f'cy="{g.get(A + "centerY")}" r="{g.get(A + "gradientRadius")}">{stop_xml}</radialGradient>')
        else:
            self.defs.append(
                f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{g.get(A + "startX")}" '
                f'y1="{g.get(A + "startY")}" x2="{g.get(A + "endX")}" y2="{g.get(A + "endY")}">{stop_xml}</linearGradient>')
        return f"url(#{gid})"

    def paint(self, el, attr):
        """The fill or stroke of a path: a colour attribute or an aapt:attr gradient."""
        value = el.get(A + attr)
        if value:
            return colour(value)
        for aapt in el.findall("{http://schemas.android.com/aapt}attr"):
            if aapt.get("name") == "android:" + attr:
                return self.gradient(aapt.find("gradient")), 1.0
        return None, 1.0

    def path(self, el):
        attrs = [f'd="{el.get(A + "pathData")}"']
        fill, fill_o = self.paint(el, "fillColor")
        attrs.append(f'fill="{fill or "none"}"')
        alpha = float(el.get(A + "fillAlpha", "1")) * fill_o
        if fill and alpha < 1:
            attrs.append(f'fill-opacity="{alpha:.3f}"')
        if el.get(A + "fillType") == "evenOdd":
            attrs.append('fill-rule="evenodd"')
        stroke, stroke_o = self.paint(el, "strokeColor")
        if stroke:
            attrs.append(f'stroke="{stroke}" stroke-width="{el.get(A + "strokeWidth", "0")}"')
            alpha = float(el.get(A + "strokeAlpha", "1")) * stroke_o
            if alpha < 1:
                attrs.append(f'stroke-opacity="{alpha:.3f}"')
            for a, svg in (("strokeLineCap", "stroke-linecap"), ("strokeLineJoin", "stroke-linejoin"),
                           ("strokeMiterLimit", "stroke-miterlimit")):
                if el.get(A + a):
                    attrs.append(f'{svg}="{el.get(A + a)}"')
        return "<path " + " ".join(attrs) + "/>"

    def group(self, el):
        px, py = float(el.get(A + "pivotX", "0")), float(el.get(A + "pivotY", "0"))
        t = []
        if el.get(A + "translateX") or el.get(A + "translateY"):
            t.append(f'translate({el.get(A + "translateX", "0")} {el.get(A + "translateY", "0")})')
        t.append(f"translate({px} {py})")
        if el.get(A + "rotation"):
            t.append(f'rotate({el.get(A + "rotation")})')
        if el.get(A + "scaleX") or el.get(A + "scaleY"):
            t.append(f'scale({el.get(A + "scaleX", "1")} {el.get(A + "scaleY", "1")})')
        t.append(f"translate({-px} {-py})")
        return f'<g transform="{" ".join(t)}">' + self.children(el) + "</g>"

    def children(self, el):
        out = []
        for c in el:
            if c.tag == "path":
                out.append(self.path(c))
            elif c.tag == "group":
                out.append(self.group(c))
            elif c.tag == "clip-path":
                self.count += 1
                cid = f"{self.prefix}c{self.count}"
                self.defs.append(f'<clipPath id="{cid}"><path d="{c.get(A + "pathData")}"/></clipPath>')
                rest = "".join(self.children_after(el, c))
                return "".join(out) + f'<g clip-path="url(#{cid})">{rest}</g>'
        return "".join(out)

    def children_after(self, el, clip):
        after = False
        for c in el:
            if c is clip:
                after = True
                continue
            if after and c.tag == "path":
                yield self.path(c)
            elif after and c.tag == "group":
                yield self.group(c)


def vector_body(conv, path):
    root = ET.parse(path).getroot()
    if root.tag != "vector":
        raise ValueError(f"{path} is not a vector drawable")
    w, h = float(root.get(A + "viewportWidth")), float(root.get(A + "viewportHeight"))
    # Layers of an adaptive icon are 108 units; scale any other viewport to it.
    return f'<g transform="scale({108 / w} {108 / h})">' + conv.children(root) + "</g>"


def icon_svg(app, res, ref):
    conv = Converter(app.replace("-", "") + "_")
    f = resolve(res, ref)
    root = ET.parse(f).getroot()
    if root.tag == "adaptive-icon":
        body = "".join(vector_body(conv, resolve(res, root.find(layer).get(A + "drawable")))
                       for layer in ("background", "foreground"))
        view = "18 18 72 72"
    else:
        body = vector_body(conv, f)
        view = "0 0 108 108"
    defs = f"<defs>{''.join(conv.defs)}</defs>" if conv.defs else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="96" height="96">'
            f"{defs}{body}</svg>\n")


def main():
    out = pathlib.Path(__file__).resolve().parent / "icons"
    out.mkdir(exist_ok=True)
    for app, (res, ref) in APPS.items():
        svg = icon_svg(app, WORKSPACE / res, ref)
        (out / f"{app}.svg").write_text(svg)
        print(f"icons/{app}.svg")


if __name__ == "__main__":
    sys.exit(main())
