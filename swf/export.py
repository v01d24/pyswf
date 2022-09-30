"""
This module defines exporters for the SWF fileformat.
"""
from __future__ import absolute_import

from typing import Tuple

from .consts import *
from .font_exporter import FontExporter
from .font_storage import FontStorage
from .geom import *
from .svg import Svg
from .text_layout import TextLayout
from .utils import *
from .data import *
from .tag import *
from .filters import *
from lxml import objectify, html
from lxml import etree
import base64
from six.moves import map
from six.moves import range
try:
    import Image
except ImportError:
    from PIL import Image
from io import BytesIO
from six.moves import cStringIO
import math
import re
import copy
import cgi


MINIMUM_STROKE_WIDTH = 0.5

CAPS_STYLE = {
    0 : 'round',
    1 : 'butt',
    2 : 'square'
}

JOIN_STYLE = {
    0 : 'round',
    1 : 'bevel',
    2 : 'miter'
}

class DefaultShapeExporter(object):
    """
    The default (abstract) Shape exporter class.
    All shape exporters should extend this class.


    """
    def __init__(self, swf=None, debug=False, force_stroke=False):
        self.swf = None
        self.debug = debug
        self.force_stroke = force_stroke

    def begin_bitmap_fill(self, bitmap_id, matrix=None, repeat=False, smooth=False):
        pass
    def begin_fill(self, color, alpha=1.0):
        pass
    def begin_gradient_fill(self, type, colors, alphas, ratios,
                            matrix=None,
                            spreadMethod=SpreadMethod.PAD,
                            interpolationMethod=InterpolationMethod.RGB,
                            focalPointRatio=0.0):
        pass
    def line_style(self,
                    thickness=float('nan'), color=0, alpha=1.0,
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit=3.0):
        pass
    def line_gradient_style(self,
                    thickness=float('nan'), color=0, alpha=1.0,
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit=3.0,
                    type = 1, colors = [], alphas = [], ratios = [],
                    matrix=None,
                    spreadMethod=SpreadMethod.PAD,
                    interpolationMethod=InterpolationMethod.RGB,
                    focalPointRatio=0.0):
        pass
    def line_bitmap_style(self,
                    thickness=float('nan'),
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit = 3.0,
                    bitmap_id=None, matrix=None, repeat=False, smooth=False):
        pass
    def end_fill(self):
        pass

    def begin_fills(self):
        pass
    def end_fills(self):
        pass
    def begin_lines(self):
        pass
    def end_lines(self):
        pass

    def begin_shape(self):
        pass
    def end_shape(self):
        pass

    def move_to(self, x, y):
        #print "move_to", x, y
        pass
    def line_to(self, x, y):
        #print "line_to", x, y
        pass
    def curve_to(self, cx, cy, ax, ay):
        #print "curve_to", cx, cy, ax, ay
        pass

class DefaultSVGShapeExporter(DefaultShapeExporter):
    def __init__(self, defs=None):
        self.defs = defs
        self.current_draw_command = ""
        self.path_data = ""
        self._e = Svg.create_element_maker()
        super(DefaultSVGShapeExporter, self).__init__()

    def move_to(self, x, y):
        self.current_draw_command = ""
        self.path_data += "M" + \
            str(NumberUtils.round_pixels_20(x)) + " " + \
            str(NumberUtils.round_pixels_20(y)) + " "

    def line_to(self, x, y):
        if self.current_draw_command != "L":
            self.current_draw_command = "L"
            self.path_data += "L"
        self.path_data += "" + \
            str(NumberUtils.round_pixels_20(x)) + " " + \
            str(NumberUtils.round_pixels_20(y)) + " "

    def curve_to(self, cx, cy, ax, ay):
        if self.current_draw_command != "Q":
            self.current_draw_command = "Q"
            self.path_data += "Q"
        self.path_data += "" + \
            str(NumberUtils.round_pixels_20(cx)) + " " + \
            str(NumberUtils.round_pixels_20(cy)) + " " + \
            str(NumberUtils.round_pixels_20(ax)) + " " + \
            str(NumberUtils.round_pixels_20(ay)) + " "

    def begin_bitmap_fill(self, bitmap_id, matrix=None, repeat=False, smooth=False):
        self.finalize_path()

    def begin_fill(self, color, alpha=1.0):
        self.finalize_path()

    def end_fill(self):
        pass
        #self.finalize_path()

    def begin_fills(self):
        pass
    def end_fills(self):
        self.finalize_path()

    def begin_gradient_fill(self, type, colors, alphas, ratios,
                            matrix=None,
                            spreadMethod=SpreadMethod.PAD,
                            interpolationMethod=InterpolationMethod.RGB,
                            focalPointRatio=0.0):
        self.finalize_path()

    def line_style(self,
                    thickness=float('nan'), color=0, alpha=1.0,
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit=3.0):
        self.finalize_path()

    def end_lines(self):
        self.finalize_path()

    def end_shape(self):
        self.finalize_path()

    def finalize_path(self):
        self.current_draw_command = ""
        self.path_data = ""

class SVGShapeExporter(DefaultSVGShapeExporter):
    def __init__(self):
        self.path = None
        self.num_patterns = 0
        self.num_gradients = 0
        self._gradients = {}
        self._gradient_ids = {}
        self.paths = {}
        self.fills_ended = False
        super(SVGShapeExporter, self).__init__()

    def begin_shape(self):
        self.g = self._e.g()

    def begin_fill(self, color, alpha=1.0):
        self.finalize_path()
        self.path.set("fill", ColorUtils.to_rgb_string(color))
        if alpha < 1.0:
            self.path.set("fill-opacity", str(alpha))
        elif self.force_stroke:
            self.path.set("stroke", ColorUtils.to_rgb_string(color))
            self.path.set("stroke-width", "1")
        else:
            self.path.set("stroke", "none")

    def begin_gradient_fill(self, type, colors, alphas, ratios,
                            matrix=None,
                            spreadMethod=SpreadMethod.PAD,
                            interpolationMethod=InterpolationMethod.RGB,
                            focalPointRatio=0.0):
        self.finalize_path()
        gradient_id = self.export_gradient(type, colors, alphas, ratios, matrix, spreadMethod, interpolationMethod, focalPointRatio)
        self.path.set("stroke", "none")
        self.path.set("fill", "url(#%s)" % gradient_id)

    def export_gradient(self, type, colors, alphas, ratios,
                        matrix=None,
                        spreadMethod=SpreadMethod.PAD,
                        interpolationMethod=InterpolationMethod.RGB,
                        focalPointRatio=0.0):
        self.num_gradients += 1
        gradient_id = "gradient%d" % self.num_gradients
        gradient = self._e.linearGradient() if type == GradientType.LINEAR \
            else self._e.radialGradient()
        gradient.set("gradientUnits", "userSpaceOnUse")

        if type == GradientType.LINEAR:
            gradient.set("x1", "-819.2")
            gradient.set("x2", "819.2")
        else:
            gradient.set("r", "819.2")
            gradient.set("cx", "0")
            gradient.set("cy", "0")
            if focalPointRatio < 0.0 or focalPointRatio > 0.0:
                gradient.set("fx", str(819.2 * focalPointRatio))
                gradient.set("fy", "0")

        if spreadMethod == SpreadMethod.PAD:
            gradient.set("spreadMethod", "pad")
        elif spreadMethod == SpreadMethod.REFLECT:
            gradient.set("spreadMethod", "reflect")
        elif spreadMethod == SpreadMethod.REPEAT:
            gradient.set("spreadMethod", "repeat")

        if interpolationMethod == InterpolationMethod.LINEAR_RGB:
            gradient.set("color-interpolation", "linearRGB")

        if matrix is not None:
            sm = _swf_matrix_to_svg_matrix(matrix)
            gradient.set("gradientTransform", sm);

        for i in range(0, len(colors)):
            entry = self._e.stop()
            offset = ratios[i] / 255.0
            entry.set("offset", str(offset))
            if colors[i] != 0.0:
                entry.set("stop-color", ColorUtils.to_rgb_string(colors[i]))
            if alphas[i] != 1.0:
                entry.set("stop-opacity", str(alphas[i]))
            gradient.append(entry)

        # prevent same gradient in <defs />
        key = etree.tostring(gradient)
        if key in self._gradients:
            gradient_id = self._gradient_ids[key]
        else:
            self._gradients[key] = copy.copy(gradient)
            self._gradient_ids[key] = gradient_id
            gradient.set("id", gradient_id)
            self.defs.append(gradient)

        return gradient_id

    def export_pattern(self, bitmap_id, matrix, repeat=False, smooth=False):
        self.num_patterns += 1
        bitmap_id = "c%d" % bitmap_id
        e = self.defs.xpath("./svg:image[@id='%s']" % bitmap_id, namespaces=Svg.NS)
        if len(e) < 1:
            raise Exception("SVGShapeExporter::begin_bitmap_fill Could not find bitmap!")
        image = e[0]
        pattern_id = "pat%d" % (self.num_patterns)
        pattern = self._e.pattern()
        pattern.set("id", pattern_id)
        pattern.set("width", image.get("width"))
        pattern.set("height", image.get("height"))
        pattern.set("patternUnits", "userSpaceOnUse")
        #pattern.set("patternContentUnits", "objectBoundingBox")
        if matrix is not None:
            pattern.set("patternTransform", _swf_matrix_to_svg_matrix(matrix, True, True, True))
            pass
        use = self._e.use()
        use.set(Svg.xlink_prefix("href"), "#%s" % bitmap_id)
        pattern.append(use)
        self.defs.append(pattern)

        return pattern_id

    def begin_bitmap_fill(self, bitmap_id, matrix=None, repeat=False, smooth=False):
        self.finalize_path()
        pattern_id = self.export_pattern(bitmap_id, matrix, repeat, smooth)
        self.path.set("stroke", "none")
        self.path.set("fill", "url(#%s)" % pattern_id)

    def line_style(self,
                    thickness=float('nan'), color=0, alpha=1.0,
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit=3.0):
        self.finalize_path()
        self.path.set("fill", "none")
        self.path.set("stroke", ColorUtils.to_rgb_string(color))
        thickness = 1 if math.isnan(thickness) else thickness
        thickness = MINIMUM_STROKE_WIDTH if thickness < MINIMUM_STROKE_WIDTH else thickness
        self.path.set("stroke-width", str(thickness))
        if alpha < 1.0:
            self.path.set("stroke-opacity", str(alpha))

    def line_gradient_style(self,
                    thickness=float('nan'),
                    pixelHinting = False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=0, endCaps=0,
                    joints=0, miterLimit=3.0,
                    type = 1,
                    colors = [],
                    alphas = [],
                    ratios = [],
                    matrix=None,
                    spreadMethod=SpreadMethod.PAD,
                    interpolationMethod=InterpolationMethod.RGB,
                    focalPointRatio=0.0):
        self.finalize_path()
        gradient_id = self.export_gradient(type, colors, alphas, ratios, matrix, spreadMethod, interpolationMethod, focalPointRatio)
        self.path.set("fill", "none")
        self.path.set("stroke-linejoin", JOIN_STYLE[joints])
        self.path.set("stroke-linecap", CAPS_STYLE[startCaps])
        self.path.set("stroke", "url(#%s)" % gradient_id)
        thickness = 1 if math.isnan(thickness) else thickness
        thickness = MINIMUM_STROKE_WIDTH if thickness < MINIMUM_STROKE_WIDTH else thickness
        self.path.set("stroke-width", str(thickness))

    def line_bitmap_style(self,
                    thickness=float('nan'),
                    pixelHinting=False,
                    scaleMode=LineScaleMode.NORMAL,
                    startCaps=None, endCaps=None,
                    joints=None, miterLimit = 3.0,
                    bitmap_id=None, matrix=None, repeat=False, smooth=False):
        self.finalize_path()
        pattern_id = self.export_pattern(bitmap_id, matrix, repeat, smooth)
        self.path.set("fill", "none")
        self.path.set("stroke", "url(#%s)" % pattern_id)
        self.path.set("stroke-linejoin", JOIN_STYLE[joints])
        self.path.set("stroke-linecap", CAPS_STYLE[startCaps])
        thickness = 1 if math.isnan(thickness) else thickness
        thickness = MINIMUM_STROKE_WIDTH if thickness < MINIMUM_STROKE_WIDTH else thickness
        self.path.set("stroke-width", str(thickness))

    def begin_fills(self):
        self.fills_ended = False
    def end_fills(self):
        self.finalize_path()
        self.fills_ended = True

    def finalize_path(self):
        if self.path is not None and len(self.path_data) > 0:
            self.path_data = self.path_data.rstrip()
            self.path.set("d", self.path_data)
            self.g.append(self.path)
        self.path = self._e.path()
        super(SVGShapeExporter, self).finalize_path()


class BaseExporter(object):
    def __init__(self, swf=None, shape_exporter=None, force_stroke=False):
        self.shape_exporter = SVGShapeExporter() if shape_exporter is None else shape_exporter
        self.clip_depth = 0
        self.mask_id = None
        self.jpegTables = None
        self.force_stroke = force_stroke
        if swf is not None:
            self.export(swf)

    def export(self, swf, force_stroke=False):
        self.force_stroke = force_stroke
        self.export_define_shapes(swf.tags)
        self.export_display_list(self.get_display_tags(swf.tags))

    def export_define_bits(self, tag):
        image = None
        if isinstance(tag, TagDefineBitsJPEG3):

            tag.bitmapData.seek(0)
            tag.bitmapAlphaData.seek(0, 2)
            num_alpha = tag.bitmapAlphaData.tell()
            tag.bitmapAlphaData.seek(0)
            image = Image.open(tag.bitmapData)
            if num_alpha > 0:
                image_width, image_height = image.size
                if num_alpha == image_width * image_height:
                    alpha_data = tag.bitmapAlphaData.read(num_alpha)
                    alpha_layer = Image.frombytes('L', image.size, alpha_data)
                    image.putalpha(alpha_layer)
        elif isinstance(tag, TagDefineBitsJPEG2):
            tag.bitmapData.seek(0)
            image = Image.open(tag.bitmapData)
        else:
            tag.bitmapData.seek(0)
            if self.jpegTables is not None:
                buff = BytesIO()
                self.jpegTables.seek(0)
                buff.write(self.jpegTables.read())
                buff.write(tag.bitmapData.read())
                buff.seek(0)
                image = Image.open(buff)
            else:
                image = Image.open(tag.bitmapData)

        self.export_image(tag, image)

    def export_define_bits_lossless(self, tag):
        tag.bitmapData.seek(0)
        image = Image.open(tag.bitmapData)
        self.export_image(tag, image)

    def export_define_sprite(self, tag, parent=None):
        display_tags = self.get_display_tags(tag.tags)
        self.export_display_list(display_tags, parent)

    def export_define_shape(self, tag):
        self.shape_exporter.debug = isinstance(tag, TagDefineShape4)
        tag.shapes.export(self.shape_exporter)

    def export_define_font(self, tag):
        pass

    def export_define_text(self, tag):
        pass

    def export_define_edit_text(self, tag):
        pass

    def export_define_shapes(self, tags):
        for tag in tags:
            if isinstance(tag, SWFTimelineContainer):
                self.export_define_sprite(tag)
                self.export_define_shapes(tag.tags)
            elif isinstance(tag, TagDefineShape):
                self.export_define_shape(tag)
            elif isinstance(tag, TagJPEGTables):
                if tag.length > 0:
                    self.jpegTables = tag.jpegTables
            elif isinstance(tag, TagDefineBits):
                self.export_define_bits(tag)
            elif isinstance(tag, TagDefineBitsLossless):
                self.export_define_bits_lossless(tag)
            elif isinstance(tag, TagDefineFont):
                self.export_define_font(tag)
            elif isinstance(tag, TagDefineText):
                self.export_define_text(tag)
            elif isinstance(tag, TagDefineEditText):
                self.export_define_edit_text(tag)

    def export_display_list(self, tags, parent=None):
        self.clip_depth = 0
        for tag in tags:
            self.export_display_list_item(tag, parent)

    def export_display_list_item(self, tag, parent=None):
        pass

    def export_image(self, tag, image=None):
        pass

    def get_display_tags(self, tags, z_sorted=True):
        dp_tuples = []
        for tag in tags:
            if isinstance(tag, TagPlaceObject):
                dp_tuples.append((tag, tag.depth))
            elif isinstance(tag, TagShowFrame):
                break
        if z_sorted:
            dp_tuples = sorted(dp_tuples, key=lambda tag_info: tag_info[1])
        display_tags = []
        for item in dp_tuples:
            display_tags.append(item[0])
        return display_tags

    def serialize(self):
        return None

class SVGExporter(BaseExporter):
    def __init__(self, font_storage, swf=None, margin=0):
        self._font_storage = font_storage
        self._e = Svg.create_element_maker()
        self._margin = margin
        super(SVGExporter, self).__init__(swf)

    def export(self, swf, force_stroke=False):
        """ Exports the specified SWF to SVG.

        @param swf  The SWF.
        @param force_stroke Whether to force strokes on non-stroked fills.
        """
        self.svg = self._e.svg(version=Svg.SVG_VERSION)
        self.force_stroke = force_stroke
        self.defs = self._e.defs()
        self.root = self._e.g()
        self.svg.append(self.defs)
        self.svg.append(self.root)
        self.shape_exporter.defs = self.defs
        self._num_filters = 0
        self._font_exporter = FontExporter(self.defs, self._font_storage)
        self.fonts = dict([(x.characterId,x) for x in swf.all_tags_of_type(TagDefineFont)])

        # GO!
        super(SVGExporter, self).export(swf, force_stroke)

        # Setup svg @width, @height and @viewBox
        # and add the optional margin
        frame_size = swf.header.frame_size
        xmin = frame_size.xmin / PIXELS_PER_TWIP
        ymin = frame_size.ymin / PIXELS_PER_TWIP
        xmax = frame_size.xmax / PIXELS_PER_TWIP
        ymax = frame_size.ymax / PIXELS_PER_TWIP
        frame_width = xmax - xmin
        frame_height = ymax - ymin
        self.svg.set("width", "%dpx" % round(frame_width))
        self.svg.set("height", "%dpx" % round(frame_height))
        if self._margin > 0:
            self.bounds.grow(self._margin)
        vb = [xmin, ymin, xmax, ymax]
        self.svg.set("viewBox", "%s" % " ".join(map(str, vb)))

        # Return the SVG as StringIO
        return self._serialize()

    def _serialize(self):
        return etree.tostring(self.svg, encoding='utf-8', xml_declaration=True)

    def export_define_sprite(self, tag, parent=None):
        id = "c%d"%tag.characterId
        g = self._e.g(id=id)
        g.set("data-type", "sprite")
        self.defs.append(g)
        self.clip_depth = 0
        super(SVGExporter, self).export_define_sprite(tag, g)

    def export_define_font(self, tag):
        self._font_exporter.export_font(tag)

    def export_define_text(self, tag: TagDefineText) -> None:
        g = self._e.g(id="c{0}".format(int(tag.characterId)))
        g.set("data-type", "text")
        g.set("data-bounds", self.serialize_bounds(tag.textBounds))
        if len(tag.records) > 0:
            font_size_min = min(r.textHeight for r in tag.records) / PIXELS_PER_TWIP
            font_size_max = max(r.textHeight for r in tag.records) / PIXELS_PER_TWIP
            if font_size_min == font_size_max:
                g.set("data-font_size", str(font_size_min))
            else:
                g.set("data-font_size_min", str(font_size_min))
                g.set("data-font_size_max", str(font_size_max))

        x = xmin = tag.textBounds.xmin/PIXELS_PER_TWIP
        y = ymin = tag.textBounds.ymin/PIXELS_PER_TWIP

        for rec in tag.records:
            if rec.hasXOffset:
                x = xmin + rec.xOffset/PIXELS_PER_TWIP
            if rec.hasYOffset:
                y = ymin + rec.yOffset/PIXELS_PER_TWIP

            size = rec.textHeight/PIXELS_PER_TWIP

            for glyph in rec.glyphEntries:
                use = self._e.use()
                use.set(Svg.xlink_prefix("href"), "#font_{0}_{1}".format(rec.fontId, glyph.index))

                use.set(
                    'transform',
                    "matrix({0},0,0,{0},{1},{2})".format(size, x, y)
                )

                color = ColorUtils.to_rgb_string(ColorUtils.rgb(rec.textColor))
                use.set("style", "fill: {0}; stroke: {0}".format(color))

                g.append(use)

                x = x + float(glyph.advance)/PIXELS_PER_TWIP

        self.defs.append(g)

    def export_define_edit_text(self, tag: TagDefineEditText) -> None:
        g = self._e.g(id="c{0}".format(int(tag.characterId)))
        g.set("data-type", "edit_text")
        g.set("data-bounds", self.serialize_bounds(tag.bounds))

        text, font_size = self._extract_text_and_font_size(tag)
        g.set("data-font_size", str(font_size))

        if tag.hasLayout:
            align = tag.align
        else:
            align = TextLayout.ALIGN_LEFT

        if tag.hasTextColor:
            text_color = tag.textColor
        else:
            text_color = 255 << 24

        font = self.fonts[tag.fontId]
        layout = TextLayout(font)
        for char_in_layout in layout.layout_text(text, font_size, align, tag.bounds):
            index = self._font_exporter.export_glyph_by_code(font, char_in_layout.code)
            if index is None:
                continue
            use = self._e.use()
            use.set(Svg.xlink_prefix("href"), "#font_{0}_{1}".format(tag.fontId, index))
            x = char_in_layout.x / PIXELS_PER_TWIP
            y = char_in_layout.y / PIXELS_PER_TWIP
            use.set(
                'transform',
                "matrix({0},0,0,{0},{1},{2})".format(font_size, x, y)
            )

            color = ColorUtils.to_rgb_string(ColorUtils.rgb(text_color))
            use.set("style", "fill: {0}; stroke: {0}".format(color))

            g.append(use)

        self.defs.append(g)

    @staticmethod
    def _extract_text_and_font_size(edit_text: TagDefineEditText) -> Tuple[str, int]:
        tag_text = edit_text.initialText
        font_size = edit_text.fontHeight / PIXELS_PER_TWIP
        if not tag_text:
            return u'', font_size
        if not tag_text.startswith(u'<'):
            return tag_text, font_size
        text_parts = []
        tree = html.fromstring(u'<span>' + tag_text + u'</span>')
        for elem in tree.iter():
            if elem.tag == 'font':
                elem_font_size = elem.get('size')
            else:
                elem_font_size = elem.get('font-size')
            if elem_font_size is not None:
                font_size = min(font_size, int(elem_font_size))
            elem_text = elem.text.strip() if elem.text else ''
            if elem_text:
                text_parts.append(elem_text)
        return u' '.join(text_parts), font_size

    def export_define_shape(self, tag):
        self.shape_exporter.force_stroke = self.force_stroke
        super(SVGExporter, self).export_define_shape(tag)
        shape = self.shape_exporter.g
        shape.set("id", "c%d" % tag.characterId)
        shape.set("data-type", "shape")
        shape.set("data-bounds", self.serialize_bounds(tag.shape_bounds))
        self.defs.append(shape)

    def export_display_list_item(self, tag, parent=None):
        g = self._e.g()
        use = self._e.use()
        is_mask = False

        if tag.hasMatrix:
            use.set("transform", _swf_matrix_to_svg_matrix(tag.matrix))
        if tag.hasClipDepth:
            self.mask_id = "mask%d" % tag.characterId
            self.clip_depth = tag.clipDepth
            g = self._e.mask(id=self.mask_id)
            # make sure the mask is completely filled white
            paths = self.defs.xpath("./svg:g[@id='c%d']/svg:path" % tag.characterId, namespaces=Svg.NS)
            for path in paths:
                path.set("fill", "#ffffff")
        elif tag.depth <= self.clip_depth and self.mask_id is not None:
            g.set("mask", "url(#%s)" % self.mask_id)

        filters = []
        filter_cxform = None
        self._num_filters += 1
        filter_id = "filter%d" % self._num_filters
        svg_filter = self._e.filter(id=filter_id)

        if tag.hasColorTransform:
            filter_cxform = self.export_color_transform(tag.colorTransform, svg_filter)
            filters.append(filter_cxform)
        if tag.hasFilterList and len(tag.filters) > 0:
            cxform = "color-xform" if tag.hasColorTransform else None
            f = self.export_filters(tag, svg_filter, cxform)
            if len(f) > 0:
                filters.extend(f)
        if tag.hasColorTransform or (tag.hasFilterList and len(filters) > 0):
            self.defs.append(svg_filter)
            use.set("filter", "url(#%s)" % filter_id)

        use.set(Svg.xlink_prefix("href"), "#c%s" % tag.characterId)
        g.append(use)

        if is_mask:
            self.defs.append(g)
        else:
            if parent is not None:
                parent.append(g)
            else:
                self.root.append(g)
        return use

    def export_color_transform(self, cxform, svg_filter, result='color-xform'):
        fe_cxform = self._e.feColorMatrix()
        fe_cxform.set("in", "SourceGraphic")
        fe_cxform.set("type", "matrix")
        fe_cxform.set("values", " ".join(map(str, cxform.matrix)))
        fe_cxform.set("result", "cxform")

        fe_composite = self._e.feComposite(operator="in")
        fe_composite.set("in2", "SourceGraphic")
        fe_composite.set("result", result)

        svg_filter.append(fe_cxform)
        svg_filter.append(fe_composite)
        return result

    def export_filters(self, tag, svg_filter, cxform=None):
        num_filters = len(tag.filters)
        elements = []
        attr_in = None
        for i in range(0, num_filters):
            swf_filter = tag.filters[i]
            #print swf_filter
            if isinstance(swf_filter, FilterDropShadow):
                elements.append(self.export_filter_dropshadow(swf_filter, svg_filter, cxform))
                #print swf_filter.strength
                pass
            elif isinstance(swf_filter, FilterBlur):
                pass
            elif isinstance(swf_filter, FilterGlow):
                #attr_in = SVGFilterFactory.export_glow_filter(self._e, svg_filter, attr_in=attr_in)
                #elements.append(attr_in)
                pass
            elif isinstance(swf_filter, FilterBevel):
                pass
            elif isinstance(swf_filter, FilterGradientGlow):
                pass
            elif isinstance(swf_filter, FilterConvolution):
                pass
            elif isinstance(swf_filter, FilterColorMatrix):
                attr_in = SVGFilterFactory.export_color_matrix_filter(self._e, svg_filter, swf_filter.colorMatrix, svg_filter, attr_in=attr_in)
                elements.append(attr_in)
                pass
            elif isinstance(swf_filter, FilterGradientBevel):
                pass
            else:
                raise Exception("unknown filter: ", swf_filter)
        return elements

#   <filter id="test-filter" x="-50%" y="-50%" width="200%" height="200%">
#		<feGaussianBlur in="SourceAlpha" stdDeviation="6" result="blur"/>
#		<feOffset dy="0" dx="0"/>
#		<feComposite in2="SourceAlpha" operator="arithmetic"
#			k2="-1" k3="1" result="shadowDiff"/>
#		<feFlood flood-color="black" flood-opacity="1"/>
#		<feComposite in2="shadowDiff" operator="in"/>
#	</filter>;

    def export_filter_dropshadow(self, swf_filter, svg_filter, blend_in=None, result="offsetBlur"):
        gauss = self._e.feGaussianBlur()
        gauss.set("in", "SourceAlpha")
        gauss.set("stdDeviation", "6")
        gauss.set("result", "blur")
        if swf_filter.knockout:
            composite0 = self._e.feComposite(
                in2="SourceAlpha", operator="arithmetic",
                k2="-1", k3="1", result="shadowDiff")
            flood = self._e.feFlood()
            flood.set("flood-color", "black")
            flood.set("flood-opacity", "1")
            composite1 = self._e.feComposite(
                in2="shadowDiff", operator="in", result=result)
            svg_filter.append(gauss)
            svg_filter.append(composite0)
            svg_filter.append(flood)
            svg_filter.append(composite1)
        else:
            SVGFilterFactory.create_drop_shadow_filter(self._e, svg_filter,
                None,
                swf_filter.blurX/20.0,
                swf_filter.blurY/20.0,
                blend_in,
                result)
        #print etree.tostring(svg_filter, pretty_print=True)
        return result

    def export_image(self, tag, image=None):
        if image is not None:
            buff = BytesIO()
            image.save(buff, "PNG")
            buff.seek(0)
            data_url = _encode_png(buff.read())
            img = self._e.image()
            img.set("id", "c%s" % tag.characterId)
            img.set("x", "0")
            img.set("y", "0 ")
            img.set("width", "%s" % str(image.size[0]))
            img.set("height", "%s" % str(image.size[1]))
            img.set(Svg.xlink_prefix("href"), "%s" % data_url)
            self.defs.append(img)

    @staticmethod
    def serialize_bounds(bounds):
        return '{} {} {} {}'.format(
            bounds.xmin / PIXELS_PER_TWIP,
            bounds.ymin / PIXELS_PER_TWIP,
            bounds.xmax / PIXELS_PER_TWIP,
            bounds.ymax / PIXELS_PER_TWIP
        )


class SingleShapeSVGExporterMixin(object):
    def export(self, swf, shape, **export_opts):
        """ Exports the specified shape of the SWF to SVG.

        @param swf   The SWF.
        @param shape Which shape to export, either by characterId(int) or as a Tag object.
        """

        # If `shape` is given as int, find corresponding shape tag.
        if isinstance(shape, Tag):
            shape_tag = shape
        else:
            shapes = [x for x in swf.all_tags_of_type((TagDefineShape, TagDefineSprite)) if x.characterId == shape]
            if len(shapes):
                shape_tag = shapes[0]
            else:
                raise Exception("Shape %s not found" % shape)

        from swf.movie import SWF

        # find a typical use of this shape
        example_place_objects = [x for x in swf.all_tags_of_type(TagPlaceObject) if x.hasCharacter and x.characterId == shape_tag.characterId]

        if len(example_place_objects):
            place_object = example_place_objects[0]
            characters = swf.build_dictionary()
            ids_to_export = place_object.get_dependencies()
            ids_exported = set()
            tags_to_export = []

            # this had better form a dag!
            while len(ids_to_export):
                id = ids_to_export.pop()
                if id in ids_exported or id not in characters:
                    continue
                tag = characters[id]
                ids_to_export.update(tag.get_dependencies())
                tags_to_export.append(tag)
                ids_exported.add(id)
            tags_to_export.reverse()
            tags_to_export.append(place_object)
        else:
            place_object = TagPlaceObject()
            place_object.hasCharacter = True
            place_object.characterId = shape_tag.characterId
            tags_to_export = [ shape_tag, place_object ]

        stunt_swf = SWF()
        stunt_swf.tags = tags_to_export

        return super(SingleShapeSVGExporterMixin, self).export(stunt_swf, **export_opts)

class FrameSVGExporter(SVGExporter):
    def export(self, swf, **export_opts):
        """ Exports a frame of the specified SWF to SVG.

        @param swf   The SWF.
        @param frame Which frame to export, by 0-based index (int)
        """
        self.wanted_frame = export_opts.pop('frame', 0)
        return super(FrameSVGExporter, self).export(swf, **export_opts)

    def get_display_tags(self, tags, z_sorted=True):

        current_frame = 0
        frame_tags = dict() # keys are depths, values are placeobject tags
        for tag in tags:
            if isinstance(tag, TagShowFrame):
                if current_frame == self.wanted_frame:
                    break
                current_frame += 1
            elif isinstance(tag, TagPlaceObject):
                if tag.hasMove:
                    orig_tag = frame_tags.pop(tag.depth)

                    if not tag.hasCharacter:
                        tag.characterId = orig_tag.characterId
                    # this is for NamesSVGExporterMixin
                    if not tag.hasName:
                        tag.instanceName = orig_tag.instanceName
                frame_tags[tag.depth] = tag
            elif isinstance(tag, TagRemoveObject):
                del frame_tags[tag.depth]

        return super(FrameSVGExporter, self).get_display_tags(frame_tags.values(), z_sorted)


class SVGFilterFactory(object):
    # http://commons.oreilly.com/wiki/index.php/SVG_Essentials/Filters
    # http://dev.opera.com/articles/view/svg-evolution-3-applying-polish/

    @classmethod
    def create_drop_shadow_filter(cls, e, filter, attr_in=None, blurX=0, blurY=0, blend_in=None, result=None):
        gaussianBlur = SVGFilterFactory.create_gaussian_blur(e, attr_deviaton="1", result="blur-out")
        offset = SVGFilterFactory.create_offset(e, "blur-out", blurX, blurY, "the-shadow")
        blend = SVGFilterFactory.create_blend(e, blend_in, attr_in2="the-shadow", result=result)
        filter.append(gaussianBlur)
        filter.append(offset)
        filter.append(blend)
        return result

    @classmethod
    def export_color_matrix_filter(cls, e, filter, matrix, svg_filter, attr_in=None, result='color-matrix'):
        attr_in = "SourceGraphic" if attr_in is None else attr_in
        fe_cxform = e.feColorMatrix()
        fe_cxform.set("in", attr_in)
        fe_cxform.set("type", "matrix")
        fe_cxform.set("values", " ".join(map(str, matrix)))
        fe_cxform.set("result", result)
        filter.append(fe_cxform)
        #print etree.tostring(filter, pretty_print=True)
        return result

    @classmethod
    def export_glow_filter(cls, e, filter, attr_in=None, result="glow-out"):
        attr_in = "SourceGraphic" if attr_in is None else attr_in
        gaussianBlur = SVGFilterFactory.create_gaussian_blur(e, attr_in=attr_in, attr_deviaton="1", result=result)
        filter.append(gaussianBlur)
        return result

    @classmethod
    def create_blend(cls, e, attr_in=None, attr_in2="BackgroundImage", mode="normal", result=None):
        blend = e.feBlend()
        attr_in = "SourceGraphic" if attr_in is None else attr_in
        blend.set("in", attr_in)
        blend.set("in2", attr_in2)
        blend.set("mode", mode)
        if result is not None:
            blend.set("result", result)
        return blend

    @classmethod
    def create_gaussian_blur(cls, e, attr_in="SourceAlpha", attr_deviaton="3", result=None):
        gaussianBlur = e.feGaussianBlur()
        gaussianBlur.set("in", attr_in)
        gaussianBlur.set("stdDeviation", attr_deviaton)
        if result is not None:
            gaussianBlur.set("result", result)
        return gaussianBlur

    @classmethod
    def create_offset(cls, e, attr_in=None, dx=0, dy=0, result=None):
        offset = e.feOffset()
        if attr_in is not None:
            offset.set("in", attr_in)
        offset.set("dx", "%d" % round(dx))
        offset.set("dy", "%d" % round(dy))
        if result is not None:
            offset.set("result", result)
        return offset

def _encode_jpeg(data):
    return "data:image/jpeg;base64," + base64.b64encode(data).decode('utf-8')

def _encode_png(data):
    return "data:image/png;base64," + base64.b64encode(data).decode('utf-8')

def _swf_matrix_to_matrix(swf_matrix=None, need_scale=False, need_translate=True, need_rotation=False, unit_div=20.0):

    if swf_matrix is None:
        values = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
    else:
        values = swf_matrix.to_array()
        if need_rotation:
            values[1] /= unit_div
            values[2] /= unit_div
        if need_scale:
            values[0] /= unit_div
            values[3] /= unit_div
        if need_translate:
            values[4] /= unit_div
            values[5] /= unit_div

    return values

def _swf_matrix_to_svg_matrix(swf_matrix=None, need_scale=False, need_translate=True, need_rotation=False, unit_div=20.0):
    values = _swf_matrix_to_matrix(swf_matrix, need_scale, need_translate, need_rotation, unit_div)
    str_values = ",".join(map(str, values))
    return "matrix(%s)" % str_values

