"""Sphinx configuration for the Octomod documentation site.

    uv sync --group docs
    uv run --group docs sphinx-build -W docs/site docs/site/_build/html

The pages are static: notebooks are rendered with the outputs they carry, and
only a notebook that asks for it in its own metadata (`explore_record.ipynb`)
is executed at build time.
"""

project = "Octomod"
author = "the Octomod developers"
copyright = "2026, the Octomod developers"

extensions = ["myst_nb", "sphinx_design"]

myst_enable_extensions = ["colon_fence", "dollarmath", "deflist"]
myst_heading_anchors = 3

# render what the notebooks hold; a notebook opts into execution itself
nb_execution_mode = "off"
nb_execution_timeout = 300
nb_execution_raise_on_error = True

exclude_patterns = ["_build", "**/record", "**/.ipynb_checkpoints", "**/README.md"]

html_theme = "sphinx_book_theme"
html_title = "Octomod"
html_theme_options = {
    "show_toc_level": 2,
    "home_page_in_toc": True,
    # the sidebar has the search field; pydata's navbar would add a second
    "navbar_persistent": [],
}
html_static_path = ["_static"]
html_js_files = ["primary-toggle.js"]
# the engine's own HTML reports of the example run, served as they are
html_extra_path = ["_extra"]
