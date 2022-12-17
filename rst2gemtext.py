#!/usr/bin/env python3

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

    #: Contains raw text extracted from reStructuredText nodes.
    rawtext = ""

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


class GemtextTranslator(docutils.nodes.GenericNodeVisitor):
    """Translate reStructuredText text nodes to Gemini text nodes."""

    #: List of Gemtext nodes that compose the final document.
    nodes = []

    #: The node that is currently being edited.
    _current_node = None

    # ==== RST NODES ====

    # paragraph

    def visit_paragraph(self, node):
        paragraph_node = ParagraphNode()
        self._current_node = paragraph_node
        self.nodes.append(paragraph_node)

    def depart_paragraph(self, node):
        pass

    # Text (leaf)

    def visit_Text(self, node):
        self._current_node.append_text(node.astext())

    def depart_Text(self, node):
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

    visitor = None

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
