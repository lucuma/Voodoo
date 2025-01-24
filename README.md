# ![Copier](https://github.com/copier-org/copier/raw/master/img/copier-logotype.png)

[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-purple.json)](https://github.com/copier-org/copier)
[![Gitpod ready-to-code](https://img.shields.io/badge/Gitpod-ready--to--code-blue?logo=gitpod)](https://gitpod.io/#https://github.com/copier-org/copier)
[![codecov](https://codecov.io/gh/copier-org/copier/branch/master/graph/badge.svg)](https://codecov.io/gh/copier-org/copier)
[![CI](https://github.com/copier-org/copier/workflows/CI/badge.svg)](https://github.com/copier-org/copier/actions?query=branch%3Amaster)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
![Python](https://img.shields.io/pypi/pyversions/copier?logo=python&logoColor=%23959DA5)
[![PyPI](https://img.shields.io/pypi/v/copier?logo=pypi&logoColor=%23959DA5)](https://pypi.org/project/copier/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Documentation Status](https://img.shields.io/readthedocs/copier/latest?logo=readthedocs)](https://copier.readthedocs.io/en/latest)
[![](https://img.shields.io/badge/Gurubase-Ask%20Copier%20Guru-006BFF)](https://gurubase.io/g/copier)

A library and CLI app for rendering project templates.

-   Works with **local** paths and **Git URLs**.
-   Your project can include any file and Copier can dynamically replace values in any
    kind of text file.
-   It generates a beautiful output and takes care of not overwriting existing files
    unless instructed to do so.

![Sample output](https://github.com/copier-org/copier/raw/master/img/copier-output.png)

## Installation

1. Install Python 3.9 or newer.
1. Install Git 2.27 or newer.
1. To use as a CLI app: [`pipx install copier`](https://github.com/pypa/pipx) or
   [`uv tool install copier`](https://docs.astral.sh/uv/#tool-management)
1. To use as a library: `pip install copier` or `conda install -c conda-forge copier`

### Nix flake

To install latest Copier release with 100% reproducibility:

```shell
nix profile install 'https://flakehub.com/f/copier-org/copier/*.tar.gz'
```

## Quick start

To create a template:

```shell
📁 my_copier_template                        # your template project
├── 📄 copier.yml                            # your template configuration
├── 📁 .git/                                 # your template is a Git repository
├── 📁 {{project_name}}                      # a folder with a templated name
│   └── 📄 {{module_name}}.py.jinja          # a file with a templated name
└── 📄 {{_copier_conf.answers_file}}.jinja   # answers are recorded here
```

```yaml title="copier.yml"
# questions
project_name:
    type: str
    help: What is your project name?

module_name:
    type: str
    help: What is your Python module name?
```

```python+jinja title="{{project_name}}/{{module_name}}.py.jinja"
print("Hello from {{module_name}}!")
```

```yaml+jinja title="{{_copier_conf.answers_file}}.jinja"
# Changes here will be overwritten by Copier
{{ _copier_answers|to_nice_yaml -}}
```

To generate a project from the template:

-   On the command-line:

    ```shell
    copier copy path/to/project/template path/to/destination
    ```

-   Or in Python code, programmatically:

        ```python
        from copier import run_copy

        # Create a project from a local path
        run_copy("path/to/project/template", "path/to/destination")

        # Or from a Git URL.
        run_copy("https://github.com/copier-org/copier.git", "path/to/destination")

        # You can also use "gh:" as a shortcut of "https://github.com/"
        run_copy("gh:copier-org/copier.git", "path/to/destination")

        # Or "gl:" as a shortcut of "https://gitlab.com/"
        run_copy("gl:copier-org/copier.git", "path/to/destination")
        ```

    If `path/to/destination` doesn't exist, Copier will create the directory.

## Basic concepts

Copier is composed of these main concepts:

1. **Templates**. They lay out how to generate the subproject.
1. **Questionnaires**. They are configured in the template. Answers are used to generate
   projects.
1. **Projects**. This is where your real program lives. But it is usually generated
   and/or updated from a template.

Copier targets these main human audiences:

1.  **Template creators**. Programmers that repeat code too much and prefer a tool to do
    it for them.

    **_Tip:_** Copier doesn't replace the DRY principle... but sometimes you simply
    can't be DRY and you need a DRYing machine...

1.  **Template consumers**. Programmers that want to start a new project quickly, or
    that want to evolve it comfortably.

Non-humans should be happy also by using Copier's CLI or API, as long as their
expectations are the same as for those humans... and as long as they have feelings.

Templates have these goals:

1. **[Code scaffolding](<https://en.wikipedia.org/wiki/Scaffold_(programming)>)**. Help
   consumers have a working source code tree as quickly as possible. All templates allow
   scaffolding.
1. **Code lifecycle management**. When the template evolves, let consumers update their
   projects. Not all templates allow updating.

Copier tries to have a smooth learning curve that lets you create simple templates that
can evolve into complex ones as needed.

## Browse or tag public templates

You can browse public Copier templates on GitHub using
[the `copier-template` topic](https://github.com/topics/copier-template). Use them as
inspiration!

If you want your template to appear in that list, just add the topic to it! 🏷

## Show your support

If you're using Copier, consider adding the Copier badge to your project's `README.md`:

```md
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)
```

...or `README.rst`:

```rst
.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json
    :target: https://github.com/copier-org/copier
    :alt: Copier
```

...or, as HTML:

<!-- prettier-ignore-start -->
```html
<a href="https://github.com/copier-org/copier"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json" alt="Copier" style="max-width:100%;"/></a>
```
<!-- prettier-ignore-end -->

### Copier badge variations

1. Badge Grayscale Border
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-border.json)](https://github.com/copier-org/copier)

1. Badge Grayscale Inverted Border
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border.json)](https://github.com/copier-org/copier)

1. Badge Grayscale Inverted Border Orange
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

1. Badge Grayscale Inverted Border Red
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-red.json)](https://github.com/copier-org/copier)

1. Badge Grayscale Inverted Border Teal
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-teal.json)](https://github.com/copier-org/copier)

1. Badge Grayscale Inverted Border Purple
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-purple.json)](https://github.com/copier-org/copier)

1. Badge Black
   [![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-black.json)](https://github.com/copier-org/copier)

## Credits

Special thanks go to [jpsca](https://github.com/jpsca) for originally creating `Copier`.
This project would not be a thing without him.

Many thanks to [pykong](https://github.com/pykong) who took over maintainership on the
project, promoted it, and laid out the bases of what the project is today.

Big thanks also go to [yajo](https://github.com/yajo) for his relentless zest for
improving `Copier` even further.

Thanks a lot, [pawamoy](https://github.com/pawamoy) for polishing very important rough
edges and improving the documentation and UX a lot.

Also special thanks to [sisp](https://github.com/sisp) for being very helpful in
polishing documentation, fixing bugs, helping the community and cleaning up the
codebase.

And thanks to all financial supporters and folks that give us a shiny star! ⭐

<a href="https://star-history.com/#copier-org/copier&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=copier-org/copier&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=copier-org/copier&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=copier-org/copier&type=Date" />
  </picture>
</a>
