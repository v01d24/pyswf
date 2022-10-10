import string
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union, Dict

from lxml import etree
from lxml.etree import _ElementTree, _Element
from lxml.objectify import ElementMaker

from swf.geom import Matrix2
from swf.utils import StringUtils

Filling = Union[None, str, 'LinearGradient', 'Pattern']


class Svg:
    SVG_VERSION = '1.1'
    SVG_NS = 'http://www.w3.org/2000/svg'
    XLINK_NS = 'http://www.w3.org/1999/xlink'
    NS = {'svg': SVG_NS, 'xlink': XLINK_NS}

    @classmethod
    def create_element_maker(cls) -> ElementMaker:
        return ElementMaker(annotate=False,
                            namespace=cls.SVG_NS,
                            nsmap={None: cls.SVG_NS, 'xlink': cls.XLINK_NS})

    @classmethod
    def svg_prefix(cls, attr):
        return '{{{}}}{}'.format(cls.SVG_NS, attr)

    @classmethod
    def xlink_prefix(cls, attr):
        return '{{{}}}{}'.format(cls.XLINK_NS, attr)

    __slots__ = ('_tree', '_elem', '_definitions', '_view_box', '_root_group')

    @classmethod
    def parse(cls, path: str):
        with open(path, 'rt') as f:
            return cls(etree.parse(f))

    def __init__(self, tree: _ElementTree) -> None:
        self._tree = tree
        root = tree.getroot()
        self._elem = root
        self._view_box = RectParser.parse(root.get('viewBox'))
        self._definitions = Definitions(root.find('.//{http://www.w3.org/2000/svg}defs'))
        self._root_group = None

    @property
    def root_elem(self):
        return self._elem

    @property
    def view_box(self):
        return self._view_box

    def get_root_group(self) -> 'ContainerGroup':
        if self._root_group is not None:
            return self._root_group
        group_elem = self._elem.find('./{http://www.w3.org/2000/svg}g')
        self._root_group = ContainerGroup(group_elem, None, self._definitions)
        return self._root_group

    def save(self, path: str):
        with open(path, 'wb') as f:
            f.write(etree.tostring(self._tree, encoding='utf-8', xml_declaration=True))


class RectParser:
    @staticmethod
    def parse(s: Optional[str], matrix: Optional[Matrix2] = None) -> Optional['Rect']:
        if StringUtils.is_empty(s):
            return None
        x_min, y_min, x_max, y_max = [float(f) for f in s.split(' ')]
        if matrix is not None:
            x_min, y_min = matrix.multiply_point((x_min, y_min))
            x_max, y_max = matrix.multiply_point((x_max, y_max))
        return Rect(x_min, y_min, x_max, y_max)


class Definitions:
    __slots__ = ('_definitions',)

    def __init__(self, elem: Optional[_Element]) -> None:
        self._definitions = {}
        if elem is not None:
            self._index_children(elem, self._definitions)

    @classmethod
    def _index_children(cls, elem: _Element, definitions_map: Dict[str, _Element]):
        for child_elem in elem:
            child_id = child_elem.get('id')
            if child_id is None:
                continue
            definitions_map[child_id] = child_elem
            if child_elem.tag == Svg.svg_prefix('g'):
                cls._index_children(child_elem, definitions_map)

    def get(self, id_: str, parent_matrix: Optional[Matrix2]) -> Optional['SvgElement']:
        elem = self._definitions.get(id_)
        if elem is None:
            return None
        if elem.tag == Svg.svg_prefix('g'):
            return self._get_svg_element(elem, parent_matrix)
        if elem.tag == Svg.svg_prefix('image'):
            return Image(elem)
        if elem.tag == Svg.svg_prefix('linearGradient'):
            return LinearGradient(elem)
        if elem.tag == Svg.svg_prefix('path'):
            return Path(elem, parent_matrix, self)
        if elem.tag == Svg.svg_prefix('pattern'):
            return Pattern(elem)
        msg = 'Unsupported tag: "{}"'.format(elem.tag)
        raise RuntimeError(msg)

    def _get_svg_element(self, elem: _Element, parent_matrix: Optional[Matrix2]) -> 'SvgElement':
        elem_type = elem.get('data-type')
        if elem_type == 'shape':
            return ShapeGroup(elem, parent_matrix, self)
        elif elem_type in ('text', 'edit_text'):
            return TextGroup(elem, parent_matrix, self)
        elif elem_type == 'sprite':
            return ContainerGroup(elem, parent_matrix, self)
        return StubGroup(elem)


class SvgElement:
    __slots__ = ('_elem',)

    def __init__(self, elem):
        self._elem = elem

    @property
    def elem(self) -> _Element:
        return self._elem


class SizedSvgElement(SvgElement):
    __slots__ = ('_parent_matrix', '_bounds', '_matrix')

    def __init__(self, elem, parent_matrix: Optional[Matrix2]):
        super().__init__(elem)
        self._matrix = TransformParser.parse(elem.get('transform'), parent_matrix)
        self._bounds = RectParser.parse(elem.get('data-bounds'), self._matrix)

    @property
    def bounds(self) -> Optional['Rect']:
        return self._bounds

    @property
    def matrix(self) -> Matrix2:
        return self._matrix


class ContainerGroup(SizedSvgElement):
    def __init__(self, elem: _Element, parent_matrix: Optional[Matrix2], definitions: Definitions) -> None:
        super().__init__(elem, parent_matrix)
        self._definitions = definitions
        self._display_groups = None

    def get_display_groups(self) -> List['DisplayGroup']:
        if self._display_groups is not None:
            return self._display_groups
        self._display_groups = []
        for child_elem in self._elem:
            if child_elem.tag != Svg.svg_prefix('g'):
                continue
            child = DisplayGroup(child_elem, self.matrix, self._definitions)
            self._display_groups.append(child)
        return self._display_groups

    def remove(self, display_group: 'DisplayGroup'):
        self._elem.remove(display_group.elem)
        if self._display_groups is not None:
            self._display_groups.remove(display_group)


class DisplayGroup(SizedSvgElement):
    def __init__(self, elem: _Element, parent_matrix: Optional[Matrix2], definitions: Definitions) -> None:
        super().__init__(elem, parent_matrix)
        self._definitions = definitions
        self._definition_initialized = False
        self._definition = None

    def get_definition(self) -> Optional['SizedSvgElement']:
        if self._definition_initialized:
            return self._definition
        child_elements = self._elem.getchildren()
        assert len(child_elements) == 1
        child_elem = child_elements[0]
        assert child_elem.tag == Svg.svg_prefix('use')
        referenced_id = child_elem.get(Svg.xlink_prefix('href'))[1:]
        use_matrix = TransformParser.parse(child_elem.get('transform'), self.matrix)
        definition = self._definitions.get(referenced_id, use_matrix)
        assert definition is None or isinstance(definition, SizedSvgElement)
        self._definition_initialized = True
        self._definition = definition
        return self._definition


class ShapeGroup(SizedSvgElement):
    def __init__(self, elem: _Element, parent_matrix: Optional[Matrix2], definitions: Definitions) -> None:
        super().__init__(elem, parent_matrix)
        self._definitions = definitions
        self._paths = None

    def get_paths(self) -> List['Path']:
        if self._paths is not None:
            return self._paths
        self._paths = []
        for child_elem in self._elem:
            assert child_elem.tag == Svg.svg_prefix('path')
            path = Path(child_elem, self._matrix, self._definitions)
            self._paths.append(path)
        return self._paths

    def remove_path(self, path: 'Path'):
        self.elem.remove(path.elem)
        if self._paths is not None:
            self._paths.remove(path)


class TextGroup(SizedSvgElement):
    def __init__(self, elem, parent_matrix: Optional[Matrix2], definitions: Definitions) -> None:
        super().__init__(elem, parent_matrix)
        self._definitions = definitions
        self._char_paths = None
        self._trimmed_length = None
        self._real_bounds = None

    def get_font_size_max(self) -> Optional[float]:
        min_font_size_str = self._elem.get('data-font_size_max')
        if StringUtils.is_empty(min_font_size_str):
            return None
        return float(min_font_size_str)

    def get_font_name(self):
        return self._elem.get('data-font_name')

    def get_font_size(self) -> Optional[float]:
        font_size_str = self._elem.get('data-font_size')
        if StringUtils.is_empty(font_size_str):
            return None
        return float(font_size_str)

    def set_font_size(self, target_font_size: float) -> None:
        bounds = self.get_real_bounds()
        center_x = (bounds.x_max + bounds.x_min) / 2
        center_y = (bounds.y_max + bounds.y_min) / 2
        font_size = self.get_font_size() or self.get_font_size_max()
        if font_size is None:
            return
        scale = target_font_size / font_size
        for use_elem in self._elem:
            self._scale_element(use_elem, center_x, center_y, scale)
        self._scale_element_attribute(self._elem, 'data-font_size', scale)
        self._scale_element_attribute(self._elem, 'data-font_size_min', scale)
        self._scale_element_attribute(self._elem, 'data-font_size_max', scale)

    def _scale_element(self, elem: _Element, center_x: float, center_y: float, scale: float):
        global_matrix = TransformParser.parse(elem.get('transform'), self.matrix)
        scaled_x = center_x + (global_matrix.tx - center_x) * scale
        scaled_y = center_y + (global_matrix.ty - center_y) * scale
        matrix = TransformParser.parse(elem.get('transform'), None)
        matrix.a = matrix.a * scale
        matrix.d = matrix.d * scale
        matrix.tx += (scaled_x - global_matrix.tx) / self.matrix.a
        matrix.ty += (scaled_y - global_matrix.ty) / self.matrix.d
        elem.set('transform', MatrixSerializer.serialize(matrix))

    @staticmethod
    def _scale_element_attribute(elem: _Element, attr_name: str, scale: float):
        attr_string = elem.attrib.get(attr_name)
        if attr_string is None:
            return
        attr_value = float(attr_string) * scale
        elem.attrib[attr_name] = str(attr_value)

    def get_text_length(self) -> int:
        return len(self._elem.getchildren())

    def get_trimmed_text_length(self) -> int:
        if self._trimmed_length is not None:
            return self._trimmed_length
        first_non_space = None
        last_non_space = None
        for index, path in enumerate(self.get_char_paths()):
            if path.is_empty():  # empty path is space
                continue
            if first_non_space is None:
                first_non_space = index
            last_non_space = index
        if first_non_space is None:
            self._trimmed_length = 0
        else:
            self._trimmed_length = last_non_space - first_non_space + 1
        return self._trimmed_length

    def get_real_bounds(self) -> 'Rect':
        if self._real_bounds is not None:
            return self._real_bounds
        paths = self.get_char_paths()
        if len(paths) == 0:
            self._real_bounds = Rect(0, 0, 0, 0)
            return self._real_bounds
        matrix = paths[0].matrix
        x_min = x_max = matrix.tx
        y_min = y_max = matrix.ty
        for path in self.get_char_paths():
            matrix = path.matrix
            x_min = min(x_min, matrix.tx)
            y_min = min(y_min, matrix.ty)
            x_max = min(x_max, matrix.tx)
            y_max = min(y_max, matrix.ty)
        font_size = self.get_font_size() or self.get_font_size_max() or 0
        self._real_bounds = Rect(x_min, y_min - font_size, x_max + font_size, y_min)
        return self._real_bounds

    def get_char_paths(self):
        if self._char_paths is not None:
            return self._char_paths
        char_paths = []
        for use_elem in self._elem.getchildren():
            reference_id = use_elem.get(Svg.xlink_prefix('href'))[1:]
            use_matrix = TransformParser.parse(use_elem.get('transform'), self.matrix)
            path = self._definitions.get(reference_id, use_matrix)
            if path is None:
                continue
            assert isinstance(path, Path)
            char_paths.append(path)
        self._char_paths = char_paths
        return char_paths


class Image(SvgElement):
    pass


class LinearGradient(SvgElement):
    pass


class Pattern(SvgElement):
    pass


class StubGroup(SvgElement):
    pass


class Path(SizedSvgElement):
    __slots__ = ('_definitions', '_filling_initialized', '_filling', '_commands',)

    def __init__(self, elem: _Element, parent_matrix: Optional[Matrix2], definitions: Definitions) -> None:
        super().__init__(elem, parent_matrix)
        self._definitions = definitions
        self._filling_initialized = False
        self._filling = None
        self._commands = None

    @property
    def bounds(self) -> Optional['Rect']:
        if self._bounds is not None:
            return self._bounds
        commands = self.get_commands()
        if len(commands) == 0:
            self._bounds = Rect(0, 0, 0, 0)
            return self._bounds
        first_command = commands[0]
        assert isinstance(first_command, MoveTo)
        x_min = first_command.gx
        y_min = first_command.gy
        x_max = first_command.gx
        y_max = first_command.gy
        for command in commands[1:]:
            assert isinstance(command, MoveTo) or isinstance(command, LineTo) or isinstance(command, QuadraticCurve)
            x_min = min(x_min, command.gx)
            y_min = min(y_min, command.gy)
            x_max = max(x_max, command.gx)
            y_max = max(y_max, command.gy)
        self._bounds = Rect(x_min, y_min, x_max, y_max)
        return self._bounds

    def has_filling(self) -> bool:
        return self._elem.get('fill') not in (None, '', 'none')

    def get_filling(self) -> Filling:
        if self._filling_initialized:
            return self._filling
        if not self.has_filling():
            self._set_filling(None)
            return None
        filling = self._elem.get('fill')
        if filling.startswith('#'):
            self._set_filling(filling)
            return filling
        if not filling.startswith('url('):
            msg = 'Unexpected filling: "{}"'.format(filling)
            raise RuntimeError(msg)
        filling_id = filling[5:-1]
        filling = self._definitions.get(filling_id, self.matrix)
        self._set_filling(filling)
        return filling

    def _set_filling(self, filling: Filling) -> None:
        self._filling_initialized = True
        self._filling = filling

    def is_empty(self):
        return StringUtils.is_empty(self._elem.get('d'))

    def get_commands(self) -> List['Command']:
        if self._commands is not None:
            return self._commands
        self._commands = PathParser(self._elem.get('d'), self.matrix).parse()
        return self._commands

    def set_commands(self, commands: List['Command']) -> None:
        path = PathSerializer().serialize(commands)
        self._elem.set('d', path)
        self._commands = commands


class TransformParser:
    @classmethod
    def parse(cls, s: Optional[str], parent_matrix: Optional[Matrix2]) -> Optional[Matrix2]:
        if StringUtils.is_empty(s):
            return parent_matrix
        if s.startswith('matrix('):
            return cls._parse_matrix(s, parent_matrix)
        if s.startswith('scale('):
            return cls._parse_scale(s, parent_matrix)
        msg = 'Invalid matrix: {}'.format(s)
        raise ValueError(msg)

    @classmethod
    def _parse_matrix(cls, s: Optional[str], parent_matrix: Optional[Matrix2]) -> Optional[Matrix2]:
        matrix_args = s[7:-1]
        a, b, c, d, tx, ty = [float(f.strip()) for f in matrix_args.split(',')]
        matrix = Matrix2(a, b, c, d, tx, ty)
        if parent_matrix is not None:
            matrix.prepend_matrix(parent_matrix)
        return matrix

    @classmethod
    def _parse_scale(cls, s: Optional[str], parent_matrix: Optional[Matrix2]) -> Optional[Matrix2]:
        scale = float(s[6:-1])
        matrix = Matrix2(scale, 0, 0, scale, 0, 0)
        if parent_matrix is not None:
            matrix.prepend_matrix(parent_matrix)
        return matrix


class MatrixSerializer:
    @classmethod
    def serialize(cls, matrix: Matrix2):
        return 'matrix({},{},{},{},{},{})'.format(
            matrix.a, matrix.b, matrix.c, matrix.d, matrix.tx, matrix.ty
        )


class PathParser:
    COMMAND_CHARS = set(string.ascii_letters)
    DELIMITER_CHARS = set(' ,')
    FLOAT_CHARS = set(string.digits + '-.')

    def __init__(self, path: str, matrix: Optional[Matrix2]) -> None:
        self._tokens = self._tokenize_path(path)
        self._token_index = 0
        self._matrix = matrix
        self._commands = []

    def parse(self) -> List['Command']:
        while self.has_tokens_left():
            command = self.read_command()
            if command == 'M':
                self._read_moves()
            elif command == 'L':
                self._read_lines()
            elif command == 'Q':
                self._read_curves()
            else:
                msg = 'Unsupported command "{}"'.format(command)
                raise RuntimeError(msg)
        return self._commands

    def _read_moves(self) -> None:
        while self.has_tokens_left() and self.is_float():
            x = self.read_float()
            y = self.read_float()
            self._commands.append(MoveTo(self._matrix, x, y))

    def _read_lines(self) -> None:
        while self.has_tokens_left() and self.is_float():
            x = self.read_float()
            y = self.read_float()
            self._commands.append(LineTo(self._matrix, x, y))

    def _read_curves(self) -> None:
        while self.has_tokens_left() and self.is_float():
            cx = self.read_float()
            cy = self.read_float()
            ax = self.read_float()
            ay = self.read_float()
            self._commands.append(QuadraticCurve(self._matrix, cx, cy, ax, ay))

    def has_tokens_left(self) -> bool:
        return self._token_index < len(self._tokens)

    def is_command(self) -> bool:
        return self._get_current_token() in self.COMMAND_CHARS

    def read_command(self) -> str:
        token = self._get_current_token()
        if token not in self.COMMAND_CHARS:
            msg = 'Command expected, got \'{}\''.format(token)
            raise ValueError(msg)
        self._token_index += 1
        return token

    def is_float(self) -> bool:
        try:
            float(self._get_current_token())
            return True
        except ValueError:
            return False

    def read_float(self) -> float:
        token = self._get_current_token()
        try:
            value = float(token)
        except ValueError:
            msg = 'Float expected, got \'{}\''.format(token)
            raise ValueError(msg)
        self._token_index += 1
        return value

    def _get_current_token(self) -> str:
        return self._tokens[self._token_index]

    @classmethod
    def _tokenize_path(cls, path) -> List[str]:
        tokens = []
        token_start = 0
        i = 0
        for i, c in enumerate(path):
            if c in cls.DELIMITER_CHARS:
                if i > token_start:
                    tokens.append(path[token_start:i])
                token_start = i + 1
            elif c in cls.COMMAND_CHARS:
                if i > token_start:
                    tokens.append(path[token_start:i])
                tokens.append(path[i])
                token_start = i + 1
            elif c not in cls.FLOAT_CHARS:
                msg = 'Unexpected char "{}" at {}'.format(c, i)
                raise ValueError(msg)
        if i > token_start:
            tokens.append(path[token_start:])
        return tokens


class PathSerializer:
    @classmethod
    def serialize(cls, commands: List['Command']) -> str:
        path_parts = []
        last_command_letter = None
        for command in commands:
            command_letter = command.get_command_letter()
            if last_command_letter != command_letter:
                path_parts.append(command_letter)
                last_command_letter = command_letter
            for arg in command.get_args():
                path_parts.append(cls._format_coordinate(arg))
        return ' '.join(path_parts)

    @staticmethod
    def _format_coordinate(coordinate: float) -> str:
        return '{:.4g}'.format(coordinate)


@dataclass(frozen=True)
class Command:
    matrix: Optional[Matrix2]

    def get_command_letter(self) -> str:
        return self.__class__.__name__[0]

    def get_args(self) -> Tuple[float, ...]:
        raise NotImplementedError()

    def _calc_global_coordinates(self,
                                 attr_local_x: str, attr_local_y: str,
                                 attr_global_x: str, attr_global_y: str) -> None:
        local_x = getattr(self, attr_local_x)
        local_y = getattr(self, attr_local_y)
        if self.matrix is not None:
            global_x, global_y = self.matrix.multiply_point((local_x, local_y))
        else:
            global_x, global_y = local_x, local_y
        object.__setattr__(self, attr_global_x, global_x)
        object.__setattr__(self, attr_global_y, global_y)


@dataclass(frozen=True)
class MoveTo(Command):
    x: float
    y: float
    gx: float = field(init=False)
    gy: float = field(init=False)

    def __post_init__(self) -> None:
        self._calc_global_coordinates('x', 'y', 'gx', 'gy')

    def get_args(self) -> Tuple[float, ...]:
        return self.x, self.y


@dataclass(frozen=True)
class LineTo(Command):
    x: float
    y: float
    gx: float = field(init=False)
    gy: float = field(init=False)

    def __post_init__(self) -> None:
        self._calc_global_coordinates('x', 'y', 'gx', 'gy')

    def get_args(self) -> Tuple[float, ...]:
        return self.x, self.y


@dataclass(frozen=True)
class QuadraticCurve(Command):
    cx: float
    cy: float
    x: float
    y: float
    gcx: float = field(init=False)
    gcy: float = field(init=False)
    gx: float = field(init=False)
    gy: float = field(init=False)

    def __post_init__(self) -> None:
        self._calc_global_coordinates('cx', 'cy', 'gcx', 'gcy')
        self._calc_global_coordinates('x', 'y', 'gx', 'gy')

    def get_args(self) -> Tuple[float, ...]:
        return self.cx, self.cy, self.x, self.y


@dataclass(frozen=True)
class Rect:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def get_width(self) -> float:
        return self.x_max - self.x_min

    def get_height(self) -> float:
        return self.y_max - self.y_min

    def contains_point(self, x, y):
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def grow(self, margin: float) -> 'Rect':
        return Rect(x_min=self.x_min - margin,
                    y_min=self.y_min - margin,
                    x_max=self.x_max + margin,
                    y_max=self.y_max + margin)

