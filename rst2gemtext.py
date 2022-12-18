#!/usr/bin/env python3

import sys
import argparse
from io import StringIO

import docutils.parsers.rst
import docutils.utils
import docutils.frontend
import docutils.nodes
import docutils.writers


def remove_newlines(text):
    """Remove new lines characters and replace them by a space.

    Supported end of line formats:

    * LF (`\n`): Unix style end of lines
    * CR LF (`\r\n`): Windows style end of lines
    * CR (`\r`): Legacy macOS end of lines (macOS 9 and earlier)

    :param str text: The text to cleanup.
    :rtype: str
    :return: The cleaned text.
    """
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def parse_rst(rst_text):
    """Parses a reStructuredText document.

    :param str rst_text: The reStructuredText to parse.
    :rtype: docutils.nodes.document
    """

    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(
        components=components
    ).get_default_values()
    document = docutils.utils.new_document("document", settings=settings)
    parser.parse(rst_text, document)
    return document


class Node:
    """Base class to implement Gemini text nodes."""

    def __init__(self):
        #: Contains raw text extracted from reStructuredText nodes.
        self.rawtext = ""

    def append_text(self, text):
        """Appends some raw text to the current node.

        :param str text: The text to append.
        """
        self.rawtext += text

    def to_gemtext(self, options={}):
        """Generates the Gemtext markup from the current node."""
        raise NotImplementedError()


class ParagraphNode(Node):
    def to_gemtext(self):
        return remove_newlines(self.rawtext)


class TitleNode(Node):
    def __init__(self, level=1):
        Node.__init__(self)
        self.level = level

    def to_gemtext(self):
        return " ".join(
            [
                "#" * max(1, min(3, self.level)),
                self.rawtext,
            ]
        )


class PreformattedTextNode(Node):
    def __init__(self, alt=""):
        Node.__init__(self)
        self.alt = alt

    def to_gemtext(self):
        return "```%s\n%s\n```" % (
            self.alt,
            self.rawtext,
        )


class GemtextTranslator(docutils.nodes.GenericNodeVisitor):
    """Translate reStructuredText text nodes to Gemini text nodes."""

    #: Nodes to ignore as there is no equivalent markup in Gemtext.
    #: NOTE: the text inside the notes will be added to the parent node.
    _NOP_NODES = [
        "strong",
        "emphasis",
        "literal",
    ]

    def __init__(self, document):
        docutils.nodes.GenericNodeVisitor.__init__(self, document)

        #: List of Gemtext nodes that compose the final document.
        self.nodes = []
        #: The node that is currently being edited.
        self._current_node = None
        #: The current section level (used for the titles level)
        self._section_level = 0

    def dispatch_visit(self, node):
        if node.tagname in self._NOP_NODES:
            return

        docutils.nodes.GenericNodeVisitor.dispatch_visit(self, node)

    def dispatch_departure(self, node):
        if node.tagname in self._NOP_NODES:
            return

        docutils.nodes.GenericNodeVisitor.dispatch_departure(self, node)

    # ==== RST NODES ====

    def visit_literal_block(self, node):
        alt = ""
        for class_ in node.attributes["classes"]:
            if class_ != "code":
                alt = class_
                break
        preformatted_text_node = PreformattedTextNode(alt=alt)
        self._current_node = preformatted_text_node
        self.nodes.append(preformatted_text_node)

    def depart_literal_block(self, node):
        pass

    # paragraph

    def visit_paragraph(self, node):
        paragraph_node = ParagraphNode()
        self._current_node = paragraph_node
        self.nodes.append(paragraph_node)

    def depart_paragraph(self, node):
        pass

    # section

    def visit_section(self, node):
        self._section_level += 1

    def depart_section(self, node):
        self._section_level -= 1

    # Text (leaf)

    def visit_Text(self, node):
        self._current_node.append_text(node.astext())

    def depart_Text(self, node):
        pass

    # title

    def visit_title(self, node):
        title_node = TitleNode(level=self._section_level)
        self._current_node = title_node
        self.nodes.append(title_node)

    def depart_title(self, node):
        pass

    # ==== DEFAULT ====

    def default_visit(self, node):
        """Override for generic, uniform traversals."""
        pass

    def default_departure(self, node):
        """Override for generic, uniform traversals."""
        pass


class GemtextWriter(docutils.writers.Writer):
    """Write Gemtext from reStructuredText ducument."""

    def __init__(self):
        docutils.writers.Writer.__init__(self)
        self.visitor = None

    def translate(self):
        self.visitor = GemtextTranslator(self.document)
        self.document.walkabout(self.visitor)
        self.output = (
            "\n\n".join([node.to_gemtext() for node in self.visitor.nodes]) + "\n"
        )


def convert(rst_text):
    """Convert the input reStructuredText to Gemtext.

    :param str rst_text: The input reStructuredText.

    :rtype: str
    :return: The converted Gemtext.
    """
    document = parse_rst(rst_text)
    output_io = StringIO()
    writer = GemtextWriter()
    writer.write(document, output_io)
    output_io.seek(0)
    return output_io.read()


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        prog="rst2gemtext",
        description="Converts reStructuredText to Gemtext (Gemini markup format)",
        epilog="Inaccurate output? Report bugs to https://github.com/flozz/rst2gemtext/issues",
    )

    parser.add_argument(
        "input_rst",
        help="the reStructuredText file to convert",
        type=argparse.FileType("r"),
    )
    parser.add_argument(
        "output_gemtext",
        help="the output Gemtext file",
        type=argparse.FileType("w"),
    )

    params = parser.parse_args(args)

    output_gemtext = convert(params.input_rst.read())
    params.output_gemtext.write(output_gemtext)


if __name__ == "__main__":
    main()
