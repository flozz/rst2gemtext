#!/usr/bin/env python3

import docutils.parsers.rst
import docutils.utils
import docutils.frontend
import docutils.nodes
import docutils.writers


def parse_rst(text):
    """Parses a reStructuredText document.

    :param str text: The reStructuredText to parse.
    :rtype: docutils.nodes.document
    """

    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(
        components=components
    ).get_default_values()
    document = docutils.utils.new_document("document", settings=settings)
    parser.parse(text, document)
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


class GemtextTranslator(docutils.nodes.GenericNodeVisitor):
    """Translate reStructuredText text nodes to Gemini text nodes."""

    #: List of Gemtext nodes that compose the final document.
    nodes = []

    #: The node that is currently being edited.
    _current_node = None

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
        self.output = "\n\n".join([node.to_gemtext() for node in self.visitor.nodes])
