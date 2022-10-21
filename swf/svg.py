from lxml.objectify import ElementMaker


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
