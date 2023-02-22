import pathlib

import pytest
import docutils.nodes

import rst2gemtext


_FIXTURES_PATH = pathlib.Path(__file__).parent / "fixtures"
_FIXTURES = list(_FIXTURES_PATH.glob("*.rst"))


class Test_remove_newline:
    # Unix end of line format
    def test_nl(self):
        assert rst2gemtext.remove_newlines("foo\nbar") == "foo bar"

    # Windows end of line format
    def test_crnl(self):
        assert rst2gemtext.remove_newlines("foo\r\nbar") == "foo bar"

    # Legacy macOS end of line format (macOS 9 and earlier)
    def test_cr(self):
        assert rst2gemtext.remove_newlines("foo\rbar") == "foo bar"


class Test_parse_rst:
    def test_parsing_rst(self):
        result = rst2gemtext.parse_rst("")
        assert isinstance(result, docutils.nodes.document)


class Test_convert:
    @pytest.mark.parametrize("input_rst_file", [f.name for f in _FIXTURES])
    def test_rst_document(self, input_rst_file):
        source_rst_path = (_FIXTURES_PATH / input_rst_file).as_posix()

        with open(source_rst_path, "r") as file_:
            input_rst = file_.read()

        with open((_FIXTURES_PATH / input_rst_file).with_suffix(".gmi"), "r") as file_:
            expected_gemtext = file_.read()

        output_gemtext = rst2gemtext.convert(input_rst, source_rst_path)
        assert output_gemtext == expected_gemtext


class Test_EnumaratedListNode:
    @pytest.mark.parametrize(
        "number,result",
        [
            (1, "a"),
            (2, "b"),
            (26, "z"),
            (27, "aa"),
            (28, "ab"),
        ],
    )
    def test_to_loweralpha(self, number, result):
        node = rst2gemtext.EnumaratedListNode(None)
        assert node._to_loweralpha(number) == result
