import flask_admin.babel
from flask_admin.babel import gettext as gettext_old
from flask_admin.babel import lazy_gettext as lazy_gettext_old
from flask_admin.babel import ngettext as ngettext_old

# from flask_babel import ngettext as n_
from flask_babel import LazyString
from flask_babel import gettext as _
from flask_babel import lazy_gettext as __


def gettext(string, **variables):

    tt = _(string, **variables)
    # print("=--", string, tt)
    if tt == string:
        return gettext_old(string, **variables)
    return tt


# def ngettext(*args, **kwargs):
#     tt = n_(*args, **kwargs)
#     if tt == string:
#         return ngettext_old(string, **variables)
#     return tt


def lazy_gettext(string, **variables):
    return LazyString(gettext, string, **variables)


flask_admin.babel.gettext = gettext
# flask_admin.babel.ngettext = ngettext
flask_admin.babel.lazy_gettext = lazy_gettext
