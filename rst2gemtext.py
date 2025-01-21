#!/usr/bin/env python3

import re
import sys
import argparse
import math
from io import StringIO

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.transforms.references
import docutils.utils
import docutils.utils.roman
import docutils.writers

# XXX Hack: monkeypatch docutils to support gemini:// URIs
import docutils.utils.urischemes

if "gemini" not in docutils.utils.urischemes.schemes:
    docutils.utils.urischemes.schemes["gemini"] = ""
# XXX


def convert_to_unix_end_of_line(text):
    """Replace Windows and old macOS end of line by Unix end of lines.

    Replaces:

    * CR LF (``\r\n``): Windows style end of lines
    * CR (``\r``): Legacy macOS end of lines (macOS 9 and earlier)

    By:

    * LF (``\n``): Unix style end of lines

    :param str text: The text to process.
    :rtype: str
    :return: The text converted with unix end of lines.

    >>> convert_to_unix_end_of_line("Windows\\r\\nmacOS 9\\rand Unix\\n\\nEOL")
    'Windows\\nmacOS 9\\nand Unix\\n\\nEOL'
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def remove_newlines(text):
    """Remove new lines characters and replace them by a space.

    Supported end of line formats:

    * LF (`\n`): Unix style end of lines
    * CR LF (`\r\n`): Windows style end of lines
    * CR (`\r`): Legacy macOS end of lines (macOS 9 and earlier)

    :param str text: The text to cleanup.
    :rtype: str
    :return: The cleaned text.

    >>> remove_newlines("Windows\\r\\nmacOS 9\\rand Unix\\n\\nEOL")
    'Windows macOS 9 and Unix  EOL'
    """
    return convert_to_unix_end_of_line(text).replace("\n", " ")


def flatten_node_tree(nodes):
    """Iterates recursively on given nodes and returns a flat list of the
    nodes.

    :param list<Node> nodes: A list of ``Node``.

    :rtype: list<Node>
    """
    result_nodes = []
    for node in nodes:
        if isinstance(node, NodeGroup):
            result_nodes += flatten_node_tree(node.nodes)
        else:
            result_nodes.append(node)
    return result_nodes


def search_lines_recursive(rst_node):
    """Search recusrively for line numbers in rst nodes.

    :param rst_node: any rst node from docutils.

    :rtype: list<Node>
    :returns: A flat list of Nodes with the ``Node.line`` attribute defined.
    """
    lines = []
    if rst_node.line:
        lines.append(rst_node)
    if rst_node.children:
        for child_rst_node in rst_node.children:
            lines += search_lines_recursive(child_rst_node)
    return lines


def get_node_end_line(rst_node):
    """Get the line where the given node ends.

    :param Node rst_node: The reStructuredText node.

    :rtype: int

    >>> class Node:
    ...    pass

    >>> node = Node()
    >>> node.line = 40
    >>> node.astext = lambda: "foobar"
    >>> get_node_end_line(node)
    40

    >>> node = Node()
    >>> node.line = 40
    >>> node.astext = lambda: "line1\\nline2\\r\\nline3\\rline4"
    >>> get_node_end_line(node)
    43
    """
    node_start_line = rst_node.line
    node_height = len(convert_to_unix_end_of_line(rst_node.astext()).split("\n"))
    node_end_line = node_start_line + node_height - 1
    return node_end_line


def parse_rst(rst_text, source_path="document"):
    """Parses a reStructuredText document.

    :param str rst_text: The reStructuredText to parse.
    :param str source_path: The path of the source reStructuredText file
                            (optional, but required if the document contains an
                            ``include`` directive)
    :rtype: docutils.nodes.document
    """
    parser = docutils.parsers.rst.Parser()
    settings = docutils.frontend.get_default_settings(docutils.parsers.rst.Parser)
    document = docutils.utils.new_document(source_path, settings=settings)
    document._original_rst = rst_text
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


class LinkNode(Node):
    def __init__(self, rst_node, refname=None, uri=None, text=None):
        Node.__init__(self, rst_node)
        self.refname = refname
        self.uri = uri
        if text:
            self.rawtext = text
        else:
            self.rawtext = uri

    def to_gemtext(self):
        if not self.uri:
            raise ValueError("Link URI not resolved!")
        if self.rawtext == self.uri:
            return "=> %s" % self.uri
        else:
            return "=> %s %s" % (self.uri, self.rawtext)


class LinkGroupNode(NodeGroup):
    pass


class SeparatorNode(Node):
    def to_gemtext(self):
        return "-" * 80


class RawNode(Node):
    def __init__(self, rst_node, format_):
        Node.__init__(self, rst_node)
        self.format = format_

    def to_gemtext(self):
        return self.rawtext


class FigureNode(NodeGroup):
    pass


class AdmonitionNode(NodeGroup):
    def __init__(self, rst_node, type_=None, title=None):
        NodeGroup.__init__(self, rst_node)
        self.type = type_
        self.title = title

    def gen_title(self):
        if self.title:
            return self.title
        if self.type == "note":
            return "📝️ Note:"
        if self.type == "hint":
            return "💡️ Hint"
        if self.type == "tip":
            return "💡️ Tip"
        if self.type == "important":
            return "‼️ Important"
        if self.type == "attention":
            return "⚠️ Attention"
        if self.type == "warning":
            return "⚠️ Warning"
        if self.type == "caution":
            return "⚠️ Caution"
        if self.type == "danger":
            return "⚠️ Danger"
        if self.type == "error":
            return "⛔️ Error"
        return ""

    def to_gemtext(self):
        result = "-" * 80
        result += "\n"
        result += self.gen_title()
        result += "\n"
        result += "-" * 80
        result += "\n"
        result += NodeGroup.to_gemtext(self)
        result += "\n"
        result += "-" * 80
        return result


class GemtextTranslator(docutils.nodes.GenericNodeVisitor):
    """Translate reStructuredText text nodes to Gemini text nodes."""

    #: Nodes to ignore as there is no equivalent markup in Gemtext.
    #: NOTE: the text inside the notes will be added to the parent node.
    _NOP_NODES = [
        "emphasis",
        "literal",
        "strong",
        "target",
    ]

    #: Nodes that should be completely ignored with their content
    _SKIPPED_NODES = [
        "field_list",  # TODO Handle fields as metadata
        "comment",
        "substitution_definition",
        "topic",  # .. contents:: (ToC)
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
        #: The node that is being skipped
        self._skipped_node = None

        # Check the document object is patched and contains the original reST
        # text. This is required for tables
        if not hasattr(document, "_original_rst"):
            raise ValueError(
                "The given document object do not contains the _original_rst attribute. "
                "Please use the rst2gemtext.parse_rst method to create the document object."
            )

    def dispatch_visit(self, rst_node):
        if self._skipped_node:
            return
        if rst_node.tagname in self._SKIPPED_NODES:
            self._skipped_node = rst_node
            return
        if rst_node.tagname in self._NOP_NODES:
            return

        docutils.nodes.GenericNodeVisitor.dispatch_visit(self, rst_node)

    def dispatch_departure(self, rst_node):
        if self._skipped_node:
            if self._skipped_node is rst_node:
                self._skipped_node = None
            return
        if rst_node.tagname in self._NOP_NODES:
            return

        docutils.nodes.GenericNodeVisitor.dispatch_departure(self, rst_node)

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

    # admonition

    def visit_admonition(self, rst_node, type_=None):
        admonition_node = AdmonitionNode(rst_node, type_)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(admonition_node)

    def depart_admonition(self, rst_node):
        nodes = self._split_nodes(rst_node)
        admonition_node = nodes.pop(0)
        if admonition_node.type is None:
            if isinstance(nodes[0], TitleNode):
                title_node = nodes.pop(0)
                admonition_node.title = title_node.rawtext
        admonition_node.nodes = nodes
        self.nodes.append(admonition_node)

    # attention (admonition)

    def visit_attention(self, rst_node):
        self.visit_admonition(rst_node, type_="attention")

    def depart_attention(self, rst_node):
        self.depart_admonition(rst_node)

    # block_quote

    def visit_block_quote(self, rst_node):
        block_quote_node = BlockQuoteNode(rst_node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(block_quote_node)

    def depart_block_quote(self, rst_node):
        nodes = self._split_nodes(rst_node)
        block_quote_node = nodes.pop(0)

        links = []

        for node in nodes:
            if type(node) is LinkNode:
                links.append(node)
            elif type(node) is LinkGroupNode:
                links.extend(node.nodes)
            else:
                block_quote_node.nodes.append(node)

        if block_quote_node.nodes:
            self.nodes.append(block_quote_node)

        if links:
            if len(links) == 1:
                self.nodes.append(links[0])
            else:
                link_group_node = LinkGroupNode(None)
                link_group_node.nodes = links
                self.nodes.append(link_group_node)

    # bullet_list

    def visit_bullet_list(self, rst_node):
        bullet_list_node = BulletListNode(rst_node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(bullet_list_node)

    def depart_bullet_list(self, rst_node):
        nodes = self._split_nodes(rst_node)
        bullet_list_node = nodes.pop(0)
        links = []
        for node in nodes:
            if type(node) is LinkNode:
                links.append(node)
            elif type(node) is LinkGroupNode:
                links.extend(node.nodes)
            else:
                bullet_list_node.nodes.append(node)
        if bullet_list_node.nodes:
            self.nodes.append(bullet_list_node)
        if links:
            if len(links) == 1:
                self.nodes.append(links[0])
            else:
                link_group_node = LinkGroupNode(None)
                link_group_node.nodes = links
                self.nodes.append(link_group_node)

    # caption

    def visit_caption(self, rst_node):
        self.visit_paragraph(rst_node)

    def depart_caption(self, rst_node):
        self.depart_paragraph(rst_node)

    # caution (admonition)

    def visit_caution(self, rst_node):
        self.visit_admonition(rst_node, type_="caution")

    def depart_caution(self, rst_node):
        self.depart_admonition(rst_node)

    # danger (admonition)

    def visit_danger(self, rst_node):
        self.visit_admonition(rst_node, type_="danger")

    def depart_danger(self, rst_node):
        self.depart_admonition(rst_node)

    # enumerated_list

    def visit_enumerated_list(self, rst_node):
        enumerated_list_node = EnumaratedListNode(
            rst_node,
            enumtype=rst_node.attributes["enumtype"],
            prefix=rst_node.attributes["prefix"],
            suffix=rst_node.attributes["suffix"],
            start=rst_node.attributes["start"] if "start" in rst_node.attributes else 1,
        )
        self._current_node = None  # To catch eventual errors
        self.nodes.append(enumerated_list_node)

    def depart_enumerated_list(self, rst_node):
        self.depart_bullet_list(rst_node)

    # error (admonition)

    def visit_error(self, rst_node):
        self.visit_admonition(rst_node, type_="error")

    def depart_error(self, rst_node):
        self.depart_admonition(rst_node)

    # figure

    def visit_figure(self, rst_node):
        figure_node = FigureNode(rst_node)
        self._current_node = None
        self.nodes.append(figure_node)

    def depart_figure(self, rst_node):
        nodes = self._split_nodes(rst_node)
        figure_node = nodes.pop(0)
        for node in nodes:
            if (
                type(node) is LinkNode
                and figure_node.nodes
                and type(figure_node.nodes[-1]) is LinkNode
            ):
                prev_node = figure_node.nodes.pop()
                if prev_node.uri == node.uri:
                    if prev_node.rawtext and not node.rawtext:
                        figure_node.nodes.append(prev_node)
                    else:
                        figure_node.nodes.append(node)
                else:
                    # Swap link / image
                    figure_node.nodes.append(node)
                    figure_node.nodes.append(prev_node)
            elif type(node) is ParagraphNode:
                caption_is_alttext = False
                for fnode in figure_node.nodes:
                    if fnode.rawtext == node.rawtext:
                        caption_is_alttext = True
                        break
                if not caption_is_alttext:
                    figure_node.nodes.append(node)
            else:
                figure_node.nodes.append(node)
        if (
            type(figure_node.nodes[0]) is LinkNode
            and type(figure_node.nodes[-1]) is ParagraphNode
        ):
            if figure_node.nodes[0].rawtext == figure_node.nodes[0].uri:
                caption = figure_node.nodes.pop()
                figure_node.nodes[0].rawtext = caption.rawtext
        self.nodes.append(figure_node)

    # hint (admonition)

    def visit_hint(self, rst_node):
        self.visit_admonition(rst_node, type_="hint")

    def depart_hint(self, rst_node):
        self.depart_admonition(rst_node)

    # image

    def visit_image(self, rst_node):
        link_node = LinkNode(
            rst_node,
            uri=rst_node.attributes["uri"],
            text=rst_node.attributes["alt"] if "alt" in rst_node.attributes else None,
        )
        self.nodes.append(link_node)

    def depart_image(self, rst_node):
        pass

    # important (admonition)

    def visit_important(self, rst_node):
        self.visit_admonition(rst_node, type_="important")

    def depart_important(self, rst_node):
        self.depart_admonition(rst_node)

    # list_item

    def visit_list_item(self, rst_node):
        list_item_node = ListItemNode(rst_node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(list_item_node)

    def depart_list_item(self, rst_node):
        nodes = self._split_nodes(rst_node)
        list_item_node = nodes.pop(0)
        for node in nodes:
            if type(node) in [BulletListNode, EnumaratedListNode]:
                self.nodes.append(list_item_node)
                self.nodes.append(node)
                list_item_node = ListItemNode(node)
            elif type(node) in [LinkNode, LinkGroupNode]:
                self.nodes.append(node)
            else:
                if list_item_node.rawtext:
                    list_item_node.append_text(" ")
                list_item_node.append_text(node.to_gemtext())
        if list_item_node.rawtext:
            self.nodes.append(list_item_node)

    # literal_block

    def visit_literal_block(self, rst_node):
        alt = ""
        for class_ in rst_node.attributes["classes"]:
            if class_ != "code":
                alt = class_
                break
        preformatted_text_node = PreformattedTextNode(rst_node, alt=alt)
        self._current_node = preformatted_text_node
        self.nodes.append(preformatted_text_node)

    def depart_literal_block(self, rst_node):
        pass

    # note (admonition)

    def visit_note(self, rst_node):
        self.visit_admonition(rst_node, type_="note")

    def depart_note(self, rst_node):
        self.depart_admonition(rst_node)

    # paragraph

    def visit_paragraph(self, rst_node):
        paragraph_node = ParagraphNode(rst_node)
        self._current_node = paragraph_node
        self.nodes.append(paragraph_node)

    def depart_paragraph(self, rst_node):
        nodes = self._split_nodes(rst_node)
        paragraph_node = nodes.pop(0)

        if len(nodes) == 1 and nodes[0].rawtext == paragraph_node.rawtext:
            self.nodes.append(nodes[0])
        else:
            if paragraph_node.to_gemtext().strip():
                self.nodes.append(paragraph_node)
            if nodes:
                link_group_node = LinkGroupNode(rst_node)
                link_group_node.nodes = nodes
                self.nodes.append(link_group_node)

    # raw

    def visit_raw(self, rst_node):
        raw_node = RawNode(rst_node, rst_node.attributes["format"])
        self._current_node = raw_node
        self.nodes.append(raw_node)

    def depart_raw(self, rst_node):
        if self.nodes[-1].format not in ["gemtext", "gmi"]:
            self.nodes.pop()

    # reference

    def visit_reference(self, rst_node):
        text = ""
        for child_node in rst_node.children:
            if child_node.tagname == "image":
                continue
            elif child_node.tagname != "#text":
                raise ValueError(
                    "Unexpected tag found in a reference: %s" % child_node.tagname
                )
            text += child_node.astext()
        text = remove_newlines(text)
        link_node = LinkNode(
            rst_node,
            refname=(
                rst_node.attributes["refname"]
                if "refname" in rst_node.attributes
                else None
            ),
            uri=(
                rst_node.attributes["refuri"]
                if "refuri" in rst_node.attributes
                else None
            ),
            text=text if text else None,
        )
        self.nodes.append(link_node)

    def depart_reference(self, rst_node):
        pass

    # section

    def visit_section(self, rst_node):
        self._section_level += 1

    def depart_section(self, rst_node):
        self._section_level -= 1

    # system_message

    def visit_system_message(self, rst_node):
        system_message_node = SystemMessageNode(
            rst_node,
            level=rst_node.attributes["level"],
            line=rst_node.attributes["line"],
            source=rst_node.attributes["source"],
            type_=rst_node.attributes["type"],
        )
        self._current_node = None  # To catch eventual errors
        self.nodes.append(system_message_node)

    def depart_system_message(self, rst_node):
        nodes = self._split_nodes(rst_node)
        system_message_node = nodes.pop(0)
        system_message_node.nodes = nodes
        self.messages.append(system_message_node)

    # table

    def visit_table(self, rst_node):
        preformatted_text_node = PreformattedTextNode(rst_node)
        self._current_node = None  # To catch eventual errors
        self.nodes.append(preformatted_text_node)

    def depart_table(self, rst_node):
        # TODO: handle links
        nodes = self._split_nodes(rst_node)
        preformatted_text_node = nodes.pop(0)

        title = ""
        line_min = math.inf
        line_max = 0

        for node in flatten_node_tree(nodes):
            if isinstance(node, TitleNode):
                title = node.rawtext
                continue
            nodes = search_lines_recursive(node.rst_node)
            for node in nodes:
                node_start_line = node.line
                node_end_line = get_node_end_line(node)
                if node_start_line < line_min:
                    line_min = node_start_line
                elif node_end_line > line_max:
                    line_max = node_end_line
        line_min -= 1
        line_max += 1

        table_lines = self.document._original_rst.split("\n")[line_min - 1 : line_max]
        indent = len(re.match(r"^(\s*).*$", table_lines[0]).group(1))

        preformatted_text_node.append_text(
            "\n".join([line[indent:] for line in table_lines])
        )

        if title:
            preformatted_text_node.alt = title

        self.nodes.append(preformatted_text_node)

    # Text (leaf)

    def visit_Text(self, rst_node):
        self._current_node.append_text(rst_node.astext())

    def depart_Text(self, rst_node):
        pass

    # tip (admonition)

    def visit_tip(self, rst_node):
        self.visit_admonition(rst_node, type_="tip")

    def depart_tip(self, rst_node):
        self.depart_admonition(rst_node)

    # title

    def visit_title(self, rst_node):
        title_node = TitleNode(rst_node, level=self._section_level)
        self._current_node = title_node
        self.nodes.append(title_node)

    def depart_title(self, rst_node):
        pass

    # transition

    def visit_transition(self, rst_node):
        self.nodes.append(SeparatorNode(rst_node))

    def depart_transition(self, rst_node):
        pass

    # warning (admonition)

    def visit_warning(self, rst_node):
        self.visit_admonition(rst_node, type_="warning")

    def depart_warning(self, rst_node):
        self.depart_admonition(rst_node)

    # ==== DEFAULT ====

    def default_visit(self, rst_node):
        """Override for generic, uniform traversals."""
        pass

    def default_departure(self, rst_node):
        """Override for generic, uniform traversals."""
        pass


class GemtextWriter(docutils.writers.Writer):
    """Write Gemtext from reStructuredText ducument."""

    def __init__(self):
        docutils.writers.Writer.__init__(self)
        self.transforms = [
            docutils.transforms.references.Substitutions,
            docutils.transforms.references.ExternalTargets,
        ]
        self.visitor = None

    def translate(self):
        self.visitor = GemtextTranslator(self.document)
        for Transform in self.transforms:
            transform = Transform(self.document)
            transform.apply()
        self.document.walkabout(self.visitor)
        self._before_translate_output_generation_hook()
        self.output = (
            "\n\n".join([node.to_gemtext() for node in self.visitor.nodes]) + "\n"
        )

    def _before_translate_output_generation_hook(self):
        """Method called just before generating the final GemText document. At
        this stage, the reStructuredText document is parsed, tranformed, and
        converted into GemText nodes.

        This method can be used by subclasses to manipulate the GemText node
        before the final document is generated.

        ::

            for node in self.visitor.nodes:
                do_something(node)
        """
        pass


def convert(rst_text, source_path="document"):
    """Convert the input reStructuredText to Gemtext.

    :param str rst_text: The input reStructuredText.
    :param str source_path: The path of the source reStructuredText file
                            (optional, but required if the document contains an
                            ``include`` directive)

    :rtype: str
    :return: The converted Gemtext.
    """
    document = parse_rst(rst_text, source_path)
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

    document = parse_rst(input_rst, source_path=params.input_rst.name)

    if params.print_xml:
        print(document.asdom().toprettyxml(indent="  "))

    writer = GemtextWriter()
    writer.write(document, params.output_gemtext)

    for message in writer.visitor.messages:
        print(message)


if __name__ == "__main__":
    main()
