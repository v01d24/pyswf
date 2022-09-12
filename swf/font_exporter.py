from typing import Optional, Dict

from lxml.objectify import ObjectifiedElement

from swf.consts import EM_SQUARE_LENGTH
from swf.data import SWFShape
from swf.font_storage import FontStorage, Font
from swf.svg import Svg
from swf.tag import TagDefineFont, TagDefineFont2


class FontExporter:
    def __init__(self, parent_elem: ObjectifiedElement, font_storage: FontStorage) -> None:
        self._parent_elem = parent_elem
        self._font_storage = font_storage
        self._e = Svg.create_element_maker()
        self._glyph_exporters = {}

    def export_font(self, font_tag: TagDefineFont) -> None:
        if isinstance(font_tag, TagDefineFont2):
            code_table = {code: index for index, code in enumerate(font_tag.codeTable)}
            font_name = font_tag.fontName
        else:
            code_table = {}
            font_name = 'None'
        font_elem = self._e.g(id='font_{}'.format(font_tag.characterId))
        self._parent_elem.append(font_elem)
        font = self._font_storage.get_or_create_font(font_name)
        glyph_exporter = GlyphExporter(font_tag.characterId, code_table, font_elem, font)
        self._glyph_exporters[font_tag.characterId] = glyph_exporter
        for index, glyph in enumerate(font_tag.glyphShapeTable):
            glyph_exporter.export_glyph(index, glyph)

    def export_glyph_if_missing(self, font_tag: TagDefineFont2, code: int):
        glyph_exporter = self._glyph_exporters.get(font_tag.characterId)
        if glyph_exporter is not None:
            glyph_exporter.export_glyph_if_missing(code)


class GlyphExporter:
    def __init__(self,
                 font_id: int,
                 code_table: Dict[int, int],
                 font_elem: ObjectifiedElement, font: Font) -> None:
        self._font_id = font_id
        self._code_table = code_table
        self._font_elem = font_elem
        self._font = font
        self._e = Svg.create_element_maker()
        self._max_glyph_index = -1

    def export_glyph(self, index, glyph) -> None:
        glyph_elem_id = self._get_glyph_elem_id(self._font_id, index)
        glyph_elem = self.glyph_to_elem(glyph)
        if glyph_elem is None:
            return
        self._add_glyph_element(glyph_elem_id, glyph_elem)
        self._max_glyph_index = max(self._max_glyph_index, index)

    def export_glyph_if_missing(self, code: int):
        glyph_index = self._code_table.get(code)
        if glyph_index is not None:
            return
        glyph_elem = self._font.get_glyph(code)
        if glyph_elem is None:
            return
        glyph_index = self._max_glyph_index + 1
        glyph_elem_id = self._get_glyph_elem_id(self._font_id, glyph_index)
        self._add_glyph_element(glyph_elem_id, glyph_elem)
        self._code_table[code] = glyph_index
        self._max_glyph_index = glyph_index

    def _add_glyph_element(self, glyph_elem_id: str, glyph_elem: ObjectifiedElement):
        glyph_elem.set('id', glyph_elem_id)
        glyph_elem.set('transform', 'scale({0})'.format(float(1) / EM_SQUARE_LENGTH))
        self._font_elem.append(glyph_elem)

    @staticmethod
    def _get_glyph_elem_id(font_id: int, glyph_index: int) -> str:
        return 'font_{}_{}'.format(font_id, glyph_index)

    @staticmethod
    def glyph_to_elem(glyph: SWFShape) -> Optional[ObjectifiedElement]:
        path_group = glyph.export().g.getchildren()
        if len(path_group) == 0:
            return None
        path = path_group[0]
        del path.attrib['stroke']
        del path.attrib['fill']
        return path
