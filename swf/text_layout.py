from typing import NamedTuple, List, Iterable

from swf.data import SWFRectangle
from swf.export import EM_SQUARE_LENGTH, PIXELS_PER_TWIP
from swf.tag import TagDefineFont2


class Line(NamedTuple):
    text: str
    width: int


class CharInLayout(NamedTuple):
    c: str
    code: int
    x: int
    y: int


class TextLayout:
    """
        Класс, располагающий символы текста в заданных границах.
        Алгоритм:
        1) Текст разбивается на токены исходя из настроек:
           - BREAK_BEFORE_CHARS (символы, с которых начинается новый токен),
           - BREAK_AFTER_CHARS (символы, завершающие токен)
           - DELIMITER_CHARS (символы-разделители, являются токенами)
        2) Разделение по строкам: токены присоединяются к строке, пока ширина строки не превышает ширину границы.
           Если токен не удается разместить, он переносится на следующую строку. Пробелы не переносятся.
        3) Строки выравниваются по горизонтали, для каждого символа рассчитываются координаты
    """

    ALIGN_LEFT = 0
    ALIGN_RIGHT = 1
    ALIGN_CENTER = 2

    BREAK_BEFORE_CHARS = set('([{')
    BREAK_AFTER_CHARS = set(')]}+-=')
    DELIMITER_CHARS = set('\r\n ')

    DEFAULT_ADVANCE = PIXELS_PER_TWIP / 2

    def __init__(self, font_tag: TagDefineFont2) -> None:
        if font_tag.hasLayout:
            codes_with_advances = zip(font_tag.codeTable, font_tag.fontAdvanceTable)
            self._advances = {c: a / EM_SQUARE_LENGTH for c, a in codes_with_advances}
            self._min_advance = min(self._advances.values())
            self._max_advance = max(self._advances.values())
        else:
            self._advances = {}
            self._min_advance = self.DEFAULT_ADVANCE
            self._max_advance = self.DEFAULT_ADVANCE

    def layout_text(self, text: str, font_size: int, align: int, bounds: SWFRectangle) -> List[CharInLayout]:
        bounds_width = bounds.xmax - bounds.xmin
        char_height = PIXELS_PER_TWIP * font_size
        y = bounds.ymin
        chars_in_layout = []
        for line in self._split_by_lines(text, font_size, bounds_width):
            line_chars = self._layout_line(line, font_size, align, bounds.xmin, y, bounds_width)
            chars_in_layout.extend(line_chars)
            y += char_height
        return chars_in_layout

    def _split_by_lines(self, text: str, font_size: int, max_width: int) -> List[str]:
        line_parts = []
        line_width = 0
        lines = []
        for token in self._tokenize(text):
            if token in ('\r', '\n'):
                if len(line_parts) > 0:
                    lines.append(u''.join(line_parts))
                    line_parts = []
                    line_width = 0
                    continue
            token_width = self._measure_text(token, font_size)
            if line_width + token_width > max_width and len(line_parts):
                lines.append(u''.join(line_parts))
                line_parts = []
                line_width = 0
                if token == ' ':
                    continue
            line_parts.append(token)
            line_width += token_width
        if len(line_parts) > 0:
            lines.append(u''.join(line_parts))
        return lines

    @classmethod
    def _tokenize(cls, s: str) -> Iterable[str]:
        token_start = 0
        i = 0
        for i, c in enumerate(s):
            if c in cls.DELIMITER_CHARS:
                if i > token_start:
                    yield s[token_start:i]
                yield s[i]
                token_start = i + 1
            elif c in cls.BREAK_BEFORE_CHARS:
                if i > token_start:
                    yield s[token_start:i]
                    token_start = i
            elif c in cls.BREAK_AFTER_CHARS:
                if i >= token_start:
                    yield s[token_start:i + 1]
                    token_start = i + 1
        if i >= token_start:
            yield s[token_start:]

    def _layout_line(self,
                     line: str,
                     font_size: int,
                     align: int,
                     x: int,
                     y: int,
                     bounds_width: int) -> List[CharInLayout]:
        line_chars = []
        line_width = self._measure_text(line, font_size)
        if align == self.ALIGN_CENTER:
            x_offset = (bounds_width - line_width) / 2
        elif align == self.ALIGN_RIGHT:
            x_offset = bounds_width - line_width
        else:
            x_offset = 0
        x += 2 * PIXELS_PER_TWIP + x_offset
        y += font_size * PIXELS_PER_TWIP
        for c in line:
            if c == ' ':
                x += self._measure_char(c, font_size)
                continue
            code = ord(c)
            if code < 32:
                continue
            char_in_layout = CharInLayout(c, code, x, y)
            line_chars.append(char_in_layout)
            char_width = self._measure_char(c, font_size)
            x += char_width
        return line_chars

    def _measure_text(self, text, font_size):
        width = 0
        for c in text:
            width += self._measure_char(c, font_size)
        return width

    def _measure_char(self, c, font_size):
        if c == ' ':
            advance = self._min_advance
        else:
            code = ord(c)
            # у цифр и букв ширина минимальная и равна половине размера шрифта
            # у иероглифов ширина максимальная и равна размеру шрифта
            default_advance = self._min_advance if code < 256 else self._max_advance
            advance = self._advances.get(code, default_advance)
            if code == 215 and advance == 10:
                advance = 20
        return advance * font_size
