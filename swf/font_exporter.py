from typing import Optional, Iterable, Tuple

from lxml.objectify import ObjectifiedElement

from swf.consts import EM_SQUARE_LENGTH
from swf.data import SWFShape
from swf.font_storage import FontStorage
from swf.svg import Svg
from swf.tag import TagDefineFont, TagDefineFont2


class FontExporterBase:
    def __init__(self, parent_elem: ObjectifiedElement) -> None:
        self._parent_elem = parent_elem
        self._e = Svg.create_element_maker()
        self._exported_font_elements = {}
        self._exported_glyph_elements = {}

    def export_font(self, font_tag: TagDefineFont) -> None:
        font_elem_id = self._get_font_elem_id(font_tag.characterId)
        font_elem = self._e.g(id=font_elem_id)
        self._parent_elem.append(font_elem)
        assert font_elem_id not in self._exported_font_elements
        self._exported_font_elements[font_elem_id] = font_elem
        for glyph_elem_id, glyph in self._iter_font_glyphs(font_tag):
            glyph_elem = self.glyph_to_elem(glyph)
            if glyph_elem is None:
                continue
            self._export_glyph_element(glyph_elem_id, glyph_elem, font_elem)

    def _export_glyph_element(self,
                              glyph_elem_id: str,
                              glyph_elem: ObjectifiedElement,
                              font_elem: ObjectifiedElement):
        glyph_elem.set('id', glyph_elem_id)
        glyph_elem.set('transform', 'scale({0})'.format(float(1) / EM_SQUARE_LENGTH))
        font_elem.append(glyph_elem)
        assert glyph_elem_id not in self._exported_glyph_elements
        self._exported_glyph_elements[glyph_elem_id] = glyph_elem

    def _get_font_elem_id(self, font_id: int) -> str:
        raise NotImplementedError()

    def _iter_font_glyphs(self, font_tag: TagDefineFont) -> Iterable[Tuple[str, SWFShape]]:
        raise NotImplementedError()

    @staticmethod
    def glyph_to_elem(glyph: SWFShape) -> Optional[ObjectifiedElement]:
        path_group = glyph.export().g.getchildren()
        if len(path_group) == 0:
            return None
        path = path_group[0]
        del path.attrib['stroke']
        del path.attrib['fill']
        return path


class FontExporter(FontExporterBase):
    def __init__(self, parent_elem: ObjectifiedElement):
        super().__init__(parent_elem)
        self._exported_font_ids = set()

    def _get_font_elem_id(self, font_id: int) -> str:
        return 'font_{}'.format(font_id)

    def _iter_font_glyphs(self, font_tag: TagDefineFont) -> Iterable[Tuple[str, SWFShape]]:
        for index, glyph in enumerate(font_tag.glyphShapeTable):
            glyph_elem_id = 'font_{}_{}'.format(font_tag.characterId, index)
            yield glyph_elem_id, glyph


class Font2Exporter(FontExporterBase):
    def __init__(self, elem: ObjectifiedElement, font_storage: FontStorage) -> None:
        super().__init__(elem)
        self._font_storage = font_storage

    def _get_font_elem_id(self, font_id: int) -> str:
        return 'font2_{}'.format(font_id)

    def _iter_font_glyphs(self, font_tag: TagDefineFont2) -> Iterable[Tuple[str, SWFShape]]:
        for code, glyph in zip(font_tag.codeTable, font_tag.glyphShapeTable):
            glyph_elem_id = self._get_glyph_elem_id(font_tag.characterId, code)
            yield glyph_elem_id, glyph

    def export_glyph_if_missing(self, font_tag: TagDefineFont2, code: int):
        glyph_elem_id = self._get_glyph_elem_id(font_tag.characterId, code)
        if glyph_elem_id in self._exported_glyph_elements:
            return
        font_elem = self._exported_font_elements[font_tag.characterId]
        font = self._font_storage.get_or_create_font(font_tag.fontName)
        glyph_elem = font.get_glyph(code)
        if glyph_elem is None:
            return
        self._export_glyph_element(glyph_elem_id, glyph_elem, font_elem)

    @staticmethod
    def _get_glyph_elem_id(font_id: int, code: int) -> str:
        return 'font2_{}_{}'.format(font_id, code)
