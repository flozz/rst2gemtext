#!/usr/bin/env python3

import sys
import argparse
from io import StringIO

import docutils.parsers.rst
import docutils.utils
import docutils.utils.roman
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

    def __init__(self, rst_node):
        #: The original reStructuredText node
        self.rst_node = rst_node
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


class NodeGroup(Node):
    """Base class to implement groups of Gemini text nodes."""

    def __init__(self, rst_node):
        Node.__init__(self, rst_node)
        #: Nodes of the group
        self.nodes = []

    def to_gemtext(self):
        return "\n".join([node.to_gemtext() for node in self.nodes])


class ParagraphNode(Node):
    def to_gemtext(self):
        return remove_newlines(self.rawtext)


class TitleNode(Node):
    def __init__(self, rst_node, level=1):
        Node.__init__(self, rst_node)
        self.level = level

    def to_gemtext(self):
        return " ".join(
            [
                "#" * max(1, min(3, self.level)),
                self.rawtext,
            ]
        )


class PreformattedTextNode(Node):
    def __init__(self, rst_node, alt=""):
        Node.__init__(self, rst_node)
        self.alt = alt

    def to_gemtext(self):
        return "```%s\n%s\n```" % (
            self.alt,
            self.rawtext,
        )


class BlockQuoteNode(NodeGroup):
    def to_gemtext(self):
        return "\n>\n".join(["> %s" % node.to_gemtext() for node in self.nodes])


class BulletListNode(NodeGroup):
    def to_gemtext(self):
        items = []
        for node in self.nodes:
            if type(node) is ListItemNode:
                items.append("* %s" % node.to_gemtext())
            else:
                items.append(node.to_gemtext())
        return "\n".join(items)


class ListItemNode(Node):
    def to_gemtext(self):
        return remove_newlines(self.rawtext)


class EnumaratedListNode(BulletListNode):
    def __init__(self, node, enumtype="arabic", prefix="", suffix=".", start=1):
        BulletListNode.__init__(self, node)
        self.enumtype = enumtype
        self.prefix = prefix
        self.suffix = suffix
        self.start = start

    def _to_arabic(self, number):
        return str(number)

    def _to_loweralpha(self, number):
        glyphs = "abcdefghijklmnopqrstuvwxyz"
        result = ""
        while number:
            number -= 1
            result += glyphs[number % len(glyphs)]
            number //= len(glyphs)
        return result[::-1]

    def _to_upperalpha(self, number):
        return self._to_loweralpha(number).upper()

    def _to_lowerroman(self, number):
        return docutils.utils.roman.toRoman(number).lower()

    def _to_upperroman(self, number):
        return docutils.utils.roman.toRoman(number)

    def to_gemtext(self):
        items = []
        i = self.start
        convertor = getattr(self, "_to_%s" % self.enumtype)
        for node in self.nodes:
            if type(node) is ListItemNode:
                items.append(
                    "* %s%s%s %s"
                    % (
                        self.prefix,
                        convertor(i),
                        self.suffix,
                        node.to_gemtext(),
                    )
                )
            else:
                items.append(node.to_gemtext())
            i += 1
        return "\n".join(items)


class SystemMessageNode(NodeGroup):
    def __init__(self, rst_node, level=1, source="document", line=0, type_="info"):
        NodeGroup.__init__(self, rst_node)
        self.level = level
        self.source = source
        self.line = line
        self.type_ = type_

    def __str__(self):
        return "%s:%i: %s: %s" % (
            self.source,
            self.line,
            self.type_,
            self.to_gemtext(),
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
        #: List of messages generated by docutils
        self.messages = []
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

    def _split_nodes(self, rst_node):
        """Split the node list on the given rst_node.
        :param rst_node: The reStructuredText node
        :rtype: list[Node]
        :return: The nodes below the rst_node
        """
        for i in range(len(self.nodes)):
            if self.nodes[i].rst_node is rst_node:
                break
        splitted = self.nodes[i:]
        self.nodes = self.nodes[:i]
        return splitted

    # ==== RST NODES ====

    # block_quote

    def visit_block_quote(self, node):
        block_quote_node = BlockQuoteNode(node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(block_quote_node)

    def depart_block_quote(self, node):
        nodes = self._split_nodes(node)
        block_quote_node = nodes.pop(0)
        block_quote_node.nodes = nodes
        self.nodes.append(block_quote_node)

    # bullet_list

    def visit_bullet_list(self, node):
        bullet_list_node = BulletListNode(node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(bullet_list_node)

    def depart_bullet_list(self, node):
        nodes = self._split_nodes(node)
        bullet_list_node = nodes.pop(0)
        bullet_list_node.nodes = nodes
        self.nodes.append(bullet_list_node)

    # enumerated_list

    def visit_enumerated_list(self, node):
        enumerated_list_node = EnumaratedListNode(
            node,
            enumtype=node.attributes["enumtype"],
            prefix=node.attributes["prefix"],
            suffix=node.attributes["suffix"],
            start=node.attributes["start"] if "start" in node.attributes else 1,
        )
        self._current_node = None  # To catch eventual errors
        self.nodes.append(enumerated_list_node)

    def depart_enumerated_list(self, node):
        nodes = self._split_nodes(node)
        enumerated_list_node = nodes.pop(0)
        enumerated_list_node.nodes = nodes
        self.nodes.append(enumerated_list_node)

    # list_item

    def visit_list_item(self, node):
        list_item_node = ListItemNode(node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(list_item_node)

    def depart_list_item(self, node):
        nodes = self._split_nodes(node)
        list_item_node = nodes.pop(0)
        for node in nodes:
            if type(node) in [BulletListNode]:
                self.nodes.append(list_item_node)
                self.nodes.append(node)
                list_item_node = ListItemNode(node)
            else:
                if list_item_node.rawtext:
                    list_item_node.append_text(" ")
                list_item_node.append_text(node.to_gemtext())
        if list_item_node.rawtext:
            self.nodes.append(list_item_node)

    # literal_block

    def visit_literal_block(self, node):
        alt = ""
        for class_ in node.attributes["classes"]:
            if class_ != "code":
                alt = class_
                break
        preformatted_text_node = PreformattedTextNode(node, alt=alt)
        self._current_node = preformatted_text_node
        self.nodes.append(preformatted_text_node)

    def depart_literal_block(self, node):
        pass

    # paragraph

    def visit_paragraph(self, node):
        paragraph_node = ParagraphNode(node)
        self._current_node = paragraph_node
        self.nodes.append(paragraph_node)

    def depart_paragraph(self, node):
        pass

    # section

    def visit_section(self, node):
        self._section_level += 1

    def depart_section(self, node):
        self._section_level -= 1

    # system_message

    def visit_system_message(self, node):
        system_message_node = SystemMessageNode(
            node,
            level=node.attributes["level"],
            line=node.attributes["line"],
            source=node.attributes["source"],
            type_=node.attributes["type"],
        )
        self._current_node = None  # To catch eventual errors
        self.nodes.append(system_message_node)

    def depart_system_message(self, node):
        nodes = self._split_nodes(node)
        system_message_node = nodes.pop(0)
        system_message_node.nodes = nodes
        self.messages.append(system_message_node)

    # Text (leaf)

    def visit_Text(self, node):
        self._current_node.append_text(node.astext())

    def depart_Text(self, node):
        pass

    # title

    def visit_title(self, node):
        title_node = TitleNode(node, level=self._section_level)
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
    parser.add_argument(
        "--print-xml",
        help="print the reStructuredText as XML DOM for debug purpose",
        action="store_true",
        default=False,
    )

    params = parser.parse_args(args)
    input_rst = params.input_rst.read()

    if params.print_xml:
        document = parse_rst(input_rst)
        print(document.asdom().toprettyxml(indent="  "))

    output_gemtext = convert(input_rst)
    params.output_gemtext.write(output_gemtext)


if __name__ == "__main__":
    main()
