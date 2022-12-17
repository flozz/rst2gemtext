import docutils.nodes
import rst2gemtext


class Test_parse_srt:
    def test_parsing_rst(self):
        result = rst2gemtext.parse_rst("")
        assert isinstance(result, docutils.nodes.document)
