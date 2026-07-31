import re
import urllib.parse
import base64
import uuid
from html.parser import HTMLParser
from html import escape as html_escape

def unicode_slug(instr: str) -> str:
    from slugify import slugify
    return slugify(instr, lowercase=False, allow_unicode=True)


def url_encode(url: str) -> str:
    return urllib.parse.quote(url)


def do_base_64(input: str) -> str:
    resp = base64.b64encode(f'{input}'.encode("utf-8"))
    return resp.decode()


def is_valid_uuid(val: str, version: int | None = None) -> bool:
    try:
        uuid.UUID(val, version=version)
    except BaseException:
        return False

    return True


def convert_dict_to_url(dict):
    return '&' + '&'.join([f'{k}={v}' for k, v in dict.items()]) if len(dict) else ''


# branding_freetext (see config_enum.py) is authored through a CKEditor
# rich-text field (super-admin only, see SettingAdmin.py) and rendered
# `|safe` verbatim to every user's usage page and into the "admin_message_html"
# API field - dropping `|safe` would break the intended rich-text feature, but
# rendering it completely unsanitized is stored script execution reachable by
# anyone who can author this field. Allowlist-sanitize instead of trusting it
# outright, same as any other "admin authors HTML shown to lower-privilege
# users" field would need.
_SANITIZE_ALLOWED_TAGS = {
    'a', 'b', 'i', 'u', 's', 'strong', 'em', 'p', 'br', 'span', 'div',
    'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
    'code', 'pre', 'sub', 'sup', 'hr',
}
_SANITIZE_ALLOWED_ATTRS = {
    'a': {'href', 'title', 'target', 'rel'},
}
_SANITIZE_UNSAFE_URL_SCHEMES = ('javascript:', 'data:', 'vbscript:')
# Browsers strip ASCII C0 controls (tab/LF/CR and friends) from *inside* a
# URL before resolving its scheme, so a naive .strip() (leading/trailing
# only) lets "java\tscript:" through as if it weren't a javascript: URL.
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x1f]')


class _HTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0  # inside a disallowed tag whose content must also be dropped (script/style)

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in _SANITIZE_ALLOWED_TAGS:
            return
        kept = []
        for name, value in attrs:
            if name not in _SANITIZE_ALLOWED_ATTRS.get(tag, set()):
                continue
            if name == 'href' and _CONTROL_CHARS_RE.sub('', (value or '')).strip().lower().startswith(_SANITIZE_UNSAFE_URL_SCHEMES):
                continue
            kept.append(f'{name}="{html_escape(value or "", quote=True)}"')
        attr_str = (' ' + ' '.join(kept)) if kept else ''
        self.out.append(f'<{tag}{attr_str}>')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _SANITIZE_ALLOWED_TAGS:
            self.out.append(f'</{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag == 'br' and not self._skip_depth:
            self.out.append('<br>')

    def handle_data(self, data):
        if not self._skip_depth:
            self.out.append(html_escape(data))


def sanitize_html(value: str | None) -> str:
    """Strip everything except a small formatting-tag allowlist - see
    _SANITIZE_ALLOWED_TAGS/_SANITIZE_ALLOWED_ATTRS above."""
    if not value:
        return ''
    parser = _HTMLSanitizer()
    parser.feed(value)
    parser.close()
    return ''.join(parser.out)

# not used
# def is_assci_alphanumeric(str):
#     for c in str:
#         if c not in string.ascii_letters + string.digits:
#             return False
#     return True
