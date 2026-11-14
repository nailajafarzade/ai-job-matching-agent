"""Convert collector HTML descriptions to analyzer-friendly plain text."""
from html.parser import HTMLParser
import re


_LINE_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.heading = False

    def handle_starttag(self, tag: str, attrs):
        if tag in _LINE_TAGS or tag == "br" or tag == "li":
            bullet_only = "".join(self.current).strip() == "-"
            if not (tag in _LINE_TAGS and bullet_only):
                self._end_line()
        if tag in _HEADING_TAGS:
            self.heading = True
        elif tag == "li":
            self.current.append("- ")

    def handle_endtag(self, tag: str):
        if tag in _LINE_TAGS:
            if tag in _HEADING_TAGS:
                text = "".join(self.current).rstrip()
                if text and not text.endswith(":"):
                    self.current.append(":")
                self.heading = False
            self._end_line()
        elif tag == "li":
            self._end_line()

    def handle_data(self, data: str):
        text = re.sub(r"\s+", " ", data)
        if text:
            self.current.append(text)

    def _end_line(self):
        text = "".join(self.current).strip()
        if text:
            self.lines.append(text)
        self.current.clear()

    def finish(self):
        self._end_line()


def html_to_text(value: str) -> str:
    """Return readable lines while keeping headings and list items distinct."""
    parser = _TextParser()
    parser.feed(value)
    parser.close()
    parser.finish()
    return "\n".join(line for line in parser.lines if line)
