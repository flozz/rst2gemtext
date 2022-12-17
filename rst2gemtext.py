#!/usr/bin/env python3

import docutils.parsers.rst
import docutils.utils
import docutils.frontend


def parse_rst(text):
    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(
        components=components
    ).get_default_values()
    document = docutils.utils.new_document("document", settings=settings)
    parser.parse(text, document)
    return document
