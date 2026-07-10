#!/usr/bin/env bash
while getopts a:n:u:d: flag
do
    case "${flag}" in
        a) author=${OPTARG};;
        n) name=${OPTARG};;
        u) urlname=${OPTARG};;
        d) description=${OPTARG};;
    esac
done

echo "Author: $author";
echo "Project Name: $name";
echo "Project URL name: $urlname";
echo "Description: $description";

# $name ends up in `rm -rf "${name}"` / `cp -R ... "${name}"` below, so it
# must be a bare package-name-shaped token, not a path (e.g. "../../etc")
# that could delete or overwrite something outside this checkout.
if ! [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Invalid project name: '$name' (must match ^[A-Za-z_][A-Za-z0-9_]*\$)" >&2
    exit 1
fi

# sed_escape: author/name/urlname/description are used as sed replacement
# text below - unescaped '/', '&', or '\' in a value would either break the
# s/// syntax or (for '&') get expanded to the matched pattern text.
sed_escape() {
    printf '%s' "$1" | sed -e 's/[&/\]/\\&/g'
}
esc_author="$(sed_escape "$author")"
esc_name="$(sed_escape "$name")"
esc_urlname="$(sed_escape "$urlname")"
esc_description="$(sed_escape "$description")"

echo "Rendering the Flask template..."
original_author="hiddify"
original_name="hiddifypanel"
original_urlname="HiddifyPanel"
original_description="Awesome hiddifypanel created by hiddify"
TEMPLATE_DIR="./.github/templates/flask"
while IFS= read -r -d '' filename
do
    sed -i "s/$original_author/$esc_author/g" "$filename"
    sed -i "s/$original_name/$esc_name/g" "$filename"
    sed -i "s/$original_urlname/$esc_urlname/g" "$filename"
    sed -i "s/$original_description/$esc_description/g" "$filename"
    echo "Renamed $filename"
done < <(find "${TEMPLATE_DIR}" -name "*.*" -not \( -name "*.git*" -prune \) -not \( -name "apply.sh" -prune \) -print0)

# Add requirements
if [ ! -f pyproject.toml ]
then
    cat ${TEMPLATE_DIR}/requirements.txt >> requirements.txt
    cat ${TEMPLATE_DIR}/requirements-test.txt >> requirements-test.txt
else
    for item in $(cat ${TEMPLATE_DIR}/requirements.txt)
    do
        poetry add "${item}"
    done
    for item in $(cat ${TEMPLATE_DIR}/requirements-test.txt)
    do
        poetry add --dev "${item}"
    done
fi

# Move module files
rm -rf "${name}"
rm -rf tests
cp -R ${TEMPLATE_DIR}/hiddifypanel "${name}"
cp -R ${TEMPLATE_DIR}/tests tests

cp ${TEMPLATE_DIR}/README.md README.md
cp ${TEMPLATE_DIR}/Containerfile Containerfile
cp ${TEMPLATE_DIR}/wsgi.py wsgi.py
cp ${TEMPLATE_DIR}/.env .env
cp ${TEMPLATE_DIR}/settings.toml settings.toml

# install
make clean

if [ ! -f pyproject.toml ]
then
    make virtualenv
    make install
    echo "Applied Flask template"
    echo "Ensure you activate your env with 'source .venv/bin/activate'"
    echo "then run 'hiddifypanel' or 'python -m hiddifypanel'"
else
    poetry install
    echo "Applied Flask template"
    echo "Ensure you activate your env with 'poetry shell'"
    echo "then run 'hiddifypanel' or 'python -m hiddifypanel' or 'poetry run hiddifypanel'"
fi

echo "README.md has instructions on how to use this Flask application."
