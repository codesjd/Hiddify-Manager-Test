from flask_admin.contrib.sqla import ModelView
from flask_admin.form import SecureForm
from flask_babel import gettext as _

from hiddifypanel import auth


class AdminLTEModelView(ModelView):
    form_base_class = SecureForm
    edit_modal = True
    create_modal = True

    list_template = "hiddify-flask-admin/modern_list.html"
    create_template = "flask-admin/model/create.html"
    edit_template = "flask-admin/model/edit.html"
    details_template = "flask-admin/model/details.html"

    create_modal_template = "flask-admin/model/modals/create.html"
    edit_modal_template = "flask-admin/model/modals/edit.html"
    details_modal_template = "flask-admin/model/modals/details.html"

    def inaccessible_callback(self, name, **kwargs):
        return auth.redirect_to_login()  # type: ignore

    def get_empty_list_message(self):
        return _("There are no items in the table.")

    def _disable_select2(self, form):
        """Render every <select> in this form as a plain native dropdown
        instead of a select2 widget.

        flask-admin's Select2Widget (used for any choice/Enum model column,
        e.g. the Outbound 'protocol' field) does
        `kwargs.setdefault('data-role', 'select2')`, and its form.js turns
        that attribute into the nested `<span class="selection">...` widget.
        Forcing render_kw['data-role'] to '' makes that setdefault a no-op,
        so the attribute renders empty and form.js' applyStyle switch matches
        no case - the field stays a normal <select>. Opt-in per ModelView
        (call from create_form/edit_form); not applied globally so pages that
        actually want select2's search box keep it.
        """
        import wtforms

        for field in form:
            if isinstance(field, wtforms.SelectField):
                field.render_kw = {**(field.render_kw or {}), "data-role": ""}
        return form
