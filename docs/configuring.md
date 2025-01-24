# Configuring a template

## Configuration sources

It is important that you understand how Copier works. It has 2 kinds of configurations:

1. **Settings** for Copier itself. This includes things as minimal Copier version
   required, which subdirectory to render, tasks to run, etc.
1. **Answers**. This is customized per template. The user answers template questions,
   and those answers are stored as variables available for the template at rendering
   time.

Copier reads **settings** from these sources, in this order of priority:

1. Command line or API arguments.
1. [The `copier.yml` file][the-copieryml-file]. Settings here always start with an
   underscore (e.g. `_min_copier_version`).

!!! info

    Some settings are _only_ available as CLI arguments, and some others _only_ as
    template configurations. Some behave differently depending on where they are
    defined. [Check the docs for each specific setting][available-settings].

Copier obtains **answers** from these sources, in this order of priority:

1. Command line or API arguments.
1. Asking the user. Notice that Copier will not ask any questions answered in the
   previous source.
1. [Answer from last execution][the-copier-answersyml-file].
1. Default values defined in [the `copier.yml` file][the-copieryml-file].

## The `copier.yml` file

The `copier.yml` (or `copier.yaml`) file is found in the root of the template, and it is
the main entrypoint for managing your template configuration. It will be read and used
for two purposes:

-   [Prompting the user for information][questions].
-   [Applying template settings][available-settings] (excluding files, setting arguments
    defaults, etc.).

### Questions

For each key found, Copier will prompt the user to fill or confirm the values before
they become available to the project template.

!!! example

    This `copier.yml` file:

    ```yaml
    name_of_the_project: My awesome project
    number_of_eels: 1234
    your_email: ""
    ```

    Will result in a questionnaire similar to:

    <pre style="font-weight: bold">
    🎤 name_of_the_project
      <span style="color:orange">My awesome project</span>
    🎤 number_of_eels (int)
      <span style="color:orange">1234</span>
    🎤 your_email
    </pre>

#### Advanced prompt formatting

Apart from the simplified format, as seen above, Copier supports a more advanced format
to ask users for data. To use it, the value must be a dict.

Supported keys:

-   **type**: User input must match this type. Options are: `bool`, `float`, `int`,
    `json`, `str`, `yaml` (default).
-   **help**: Additional text to help the user know what's this question for.
-   **choices**: To restrict possible values.

    !!! tip

        A choice value of `null` makes it become the same as its key.

    !!! tip "Validation and conditional choices"

        A choice can be validated by using the extended syntax with dict-style and
        tuple-style choices. For example:

        ```yaml title="copier.yml"
        cloud:
            type: str
            help: Which cloud provider do you use?
            choices:
                - Any
                - AWS
                - Azure
                - GCP

        iac:
            type: str
            help: Which IaC tool do you use?
            choices:
                Terraform: tf
                Cloud Formation:
                    value: cf
                    validator: "{% if cloud != 'AWS' %}Requires AWS{% endif %}"
                Azure Resource Manager:
                    value: arm
                    validator: "{% if cloud != 'Azure' %}Requires Azure{% endif %}"
                Deployment Manager:
                    value: dm
                    validator: "{% if cloud != 'GCP' %}Requires GCP{% endif %}"
        ```

        When the rendered validator is a non-empty string, the choice is disabled and
        the message is shown. Choice validation is useful when the validity of a choice
        depends on the answer to a previous question.

    !!! tip "Dynamic choices"

        Choices can be created dynamically by using a templated string which renders
        as valid list-style, dict-style, or tuple-style choices in YAML format. For
        example:

        ```yaml title="copier.yml"
        language:
            type: str
            help: Which programming language do you use?
            choices:
                - python
                - node

        dependency_manager:
            type: str
            help: Which dependency manager do you use?
            choices: |
                {%- if language == "python" %}
                - poetry
                - pipenv
                {%- else %}
                - npm
                - yarn
                {%- endif %}
        ```

        Dynamic choices can be used as an alternative approach to conditional choices
        via validators where dynamic choices hide disabled choices whereas choices
        disabled via validators are visible with along with the validator's error
        message but cannot be selected.

        When combining dynamic choices with validators, make sure to escape the
        validator template using `{% raw %}...{% endraw %}`.

    !!! warning

        You are able to use different types for each choice value, but it is not
        recommended because you can get to some weird scenarios.

        For example, try to understand this 🥴

        ```yaml title="copier.yml"
        pick_one:
            type: yaml # If you are mixing types, better be explicit
            choices:
                Nothing, thanks: "null" # Will be YAML-parsed and converted to null
                Value is key: null # Value will be converted to "Value is key"
                One and a half: 1.5
                "Yes": true
                Nope: no
                Some array: "[yaml, converts, this]"
        ```

        It's better to stick with a simple type and reason about it later in
        template code:

        ```yaml title="copier.yml"
        pick_one:
            type: str
            choices:
                Nothing, thanks: ""
                Value is key: null # Becomes "Value is key", which is a str
                One and a half: "1.5"
                "Yes": "true"
                Nope: "no"
                Some array: "[str, keeps, this, as, a, str]"
        ```

-   **multiselect**: When set to `true`, allows multiple choices. The answer will be a
    `list[T]` instead of a `T` where `T` is of type `type`.
-   **default**: Leave empty to force the user to answer. Provide a default to save them
    from typing it if it's quite common. When using `choices`, the default must be the
    choice _value_, not its _key_, and it must match its _type_. If values are quite
    long, you can use
    [YAML anchors](https://confluence.atlassian.com/bitbucket/yaml-anchors-960154027.html).
-   **secret**: When `true`, it hides the prompt displaying asterisks (`*****`) and
    doesn't save the answer in [the answers file][the-copier-answersyml-file]. When
    `true`, a default value is required.
-   **placeholder**: To provide a visual example for what would be a good value. It is
    only shown while the answer is empty, so maybe it doesn't make much sense to provide
    both `default` and `placeholder`. It must be a string.

    !!! warning

        Multiline placeholders are not supported currently, due to
        [this upstream bug](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1267).

-   **multiline**: When set to `true`, it allows multiline input. This is especially
    useful when `type` is `json` or `yaml`.

-   **validator**: Jinja template with which to validate the user input. This template
    will be rendered with the combined answers as variables; it should render _nothing_
    if the value is valid, and an error message to show to the user otherwise.

-   **when**: Condition that, if `false`, skips the question.

    If it is a boolean, it is used directly. Setting it to `false` is useful for
    creating a computed value.

    If it is a string, it is converted to boolean using a parser similar to YAML, but
    only for boolean values. The string can be [templated][prompt-templating].

    If a question is skipped, its answer is not recorded, but its default value is
    available in the render context.

    !!! example

        ```yaml title="copier.yaml"
        project_creator:
            type: str

        project_license:
            type: str
            choices:
                - GPLv3
                - Public domain

        copyright_holder:
            type: str
            default: |-
                {% if project_license == 'Public domain' -%}
                    {#- Nobody owns public projects -#}
                    nobody
                {%- else -%}
                    {#- By default, project creator is the owner -#}
                    {{ project_creator }}
                {%- endif %}
            # Only ask for copyright if project is not in the public domain
            when: "{{ project_license != 'Public domain' }}"
        ```

!!! example

    ```yaml title="copier.yml"
    love_copier:
        type: bool # This makes Copier ask for y/n
        help: Do you love Copier?
        default: yes # Without a default, you force the user to answer

    project_name:
        type: str # Any value will be treated raw as a string
        help: An awesome project needs an awesome name. Tell me yours.
        default: paradox-specifier
        validator: >-
            {% if not (project_name | regex_search('^[a-z][a-z0-9\-]+$')) %}
            project_name must start with a letter, followed one or more letters, digits or dashes all lowercase.
            {% endif %}

    rocket_launch_password:
        type: str
        secret: true # This value will not be logged into .copier-answers.yml
        placeholder: my top secret password

    # I'll avoid default and help here, but you can use them too
    age:
        type: int
        validator: "{% if age <= 0 %}Must be positive{% endif %}"

    height:
        type: float

    any_json:
        help: Tell me anything, but format it as a one-line JSON string
        type: json
        multiline: true

    any_yaml:
        help: Tell me anything, but format it as a one-line YAML string
        type: yaml # This is the default type, also for short syntax questions
        multiline: true

    your_favorite_book:
        # User will choose one of these and your template will get the value
        choices:
            - The Bible
            - The Hitchhiker's Guide to the Galaxy

    project_license:
        # User will see only the dict key and choose one, but you will
        # get the dict value in your template
        choices:
            MIT: &mit_text |
                Here I can write the full text of the MIT license.
                This will be a long text, shortened here for example purposes.
            Apache2: |
                Full text of Apache2 license.
        # When using choices, the default value is the value, **not** the key;
        # that's why I'm using the YAML anchor declared above to avoid retyping the
        # whole license
        default: *mit_text
        # You can still define the type, to make sure answers that come from --data
        # CLI argument match the type that your template expects
        type: str

    close_to_work:
        help: Do you live close to your work?
        # This format works just like the dict one
        choices:
            - [at home, I work at home]
            - [less than 10km, quite close]
            - [more than 10km, not so close]
            - [more than 100km, quite far away]
    ```

#### Prompt templating

Most of those options can be templated using Jinja.

Keep in mind that the configuration is loaded as **YAML**, so the contents must be
**valid YAML** and respect **Copier's structure**. That is why we explicitly wrap some
strings in double-quotes in the following examples.

Answers provided through interactive prompting will not be rendered with Jinja, so you
cannot use Jinja templating in your answers.

!!! example

    ```yaml title="copier.yml"
    # default
    username:
        type: str

    organization:
        type: str

    email:
        type: str
        # Notice that both `username` and `organization` have been already asked
        default: "{{ username }}@{{ organization }}.com"

    # help
    copyright_holder:
        type: str
        when: "{% if organization != 'Public domain' %}true{% endif %}"
        help: The person or entity within {{ organization }} that holds copyrights.

    # type
    target:
        type: str
        choices:
            - humans
            - machines

    user_config:
        type: "{% if target == 'humans' %}yaml{% else %}json{% endif %}"

    # choices
    title:
        type: str
        help: Your title within {{ organization }}

    contact:
        choices:
            Copyright holder: "{{ copyright_holder }}"
            CEO: Alice Bob
            CTO: Carl Dave
            "{{ title }}": "{{ username }}"
    ```

!!! warning

    Keep in mind that:

    1. You can only template inside the value...
    1. ... which must be a string to be templated.
    1. Also you won't be able to use variables that aren't yet declared.

    ```yaml title="copier.yml"
    your_age:
        type: int

    # Valid
    double_it:
        type: int
        default: "{{ your_age * 2}}"

    # Invalid, the templating occurs outside of the parameter value
    did_you_ask:
        type: str
        {% if your_age %}
        default: "yes"
        {% else %}
        placeholder: "nope"
        {% endif %}

    # Invalid, `a_random_word` wasn't answered yet
    other_random_word:
        type: str
        placeholder: "Something different to {{ a_random_word }}"

    # Invalid, YAML interprets curly braces
    a_random_word:
        type: str
        default: {{ 'hello' }}
    ```

### Include other YAML files

The `copier.yml` file supports multiple documents as well as using the `!include` tag to
include settings and questions from other YAML files. This allows you to split up a
larger `copier.yml` and enables you to reuse common partial sections from your
templates. When multiple documents are used, care has to be taken with questions and
settings that are defined in more than one document:

-   A question with the same name overwrites definitions from an earlier document.
-   Settings given in multiple documents for `exclude`, `skip_if_exists`,
    `jinja_extensions` and `secret_questions` are concatenated.
-   Other settings (such as `tasks` or `migrations`) overwrite previous definitions for
    these settings.

!!! hint

    You can use [Git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
    to sanely include shared code into templates.

!!! example

    This would be a valid `copier.yml` file:

    ```yaml title="copier.yml"
    ---
    # Copier will load all these files
    !include shared-conf/common.*.yml

    # These 3 lines split the several YAML documents
    ---
    # These two documents include common questions for these kind of projects
    !include common-questions/web-app.yml
    ---
    !include common-questions/python-project.yml
    ---

    # Here you can specify any settings or questions specific for your template
    _skip_if_exists:
        - .password.txt
    custom_question: default answer
    ```

    that includes questions and settings from:

    ```yaml title="common-questions/python-project.yml"
    version:
        type: str
        help: What is the version of your Python project?

    # Settings like `_skip_if_exists` are merged
    _skip_if_exists:
        - "pyproject.toml"
    ```

## Conditional files and directories

You can take advantage of the ability to template file and directory names to make them
"conditional", i.e. to only generate them based on the answers given by a user.

For example, you can ask users if they want to use
[pre-commit](https://pre-commit.com/):

```yaml title="copier.yml"
use_precommit:
    type: bool
    default: false
    help: Do you want to use pre-commit?
```

And then, you can generate a `.pre-commit-config.yaml` file only if they answered "yes":

```tree result="shell"
your_template
    copier.yml
    {% if use_precommit %}.pre-commit-config.yaml{% endif %}.jinja
```

!!! important

    Note that the chosen [template suffix][templates_suffix]
    **must** appear outside of the Jinja condition,
    otherwise the whole file won't be considered a template and will
    be copied as such in generated projects.

You can even use the answers of questions with [choices][advanced-prompt-formatting]:

```yaml title="copier.yml"
ci:
    type: str
    help: What Continuous Integration service do you want to use?
    choices:
        GitHub CI: github
        GitLab CI: gitlab
    default: github
```

```tree result="shell"
your_template
    copier.yml
    {% if ci == 'github' %}.github{% endif %}
        workflows
            ci.yml
    {% if ci == 'gitlab' %}.gitlab-ci.yml{% endif %}.jinja
```

!!! important

    Contrary to files, directories **must not** end with the [template suffix][templates_suffix].

!!! warning

    On Windows, double-quotes are not valid characters in file and directory paths.
    This is why we used **single-quotes** in the example above.

## Generating a directory structure

You can use answers to generate file names as well as whole directory structures.

```yaml title="copier.yml"
package:
    type: str
    help: Package name
```

```tree result="shell"
your_template
    copier.yml
    {{ package.replace('.', _copier_conf.sep) }}{{ _copier_conf.sep }}__main__.py.jinja
```

If you answer

> your_package.cli.main

Copier will generate this structure:

```tree result="shell"
your_project
    your_package
        cli
            main
                __main__.py
```

You can either use any separator, like `.`, and replace it with `_copier_conf.sep`, like
in the example above, or just use `/` in the answer (works on Windows too).

## Importing Jinja templates and macros

You can
[include templates](https://jinja.palletsprojects.com/en/3.1.x/templates/#include) and
[import macros](https://jinja.palletsprojects.com/en/3.1.x/templates/#import) to reduce
code duplication. A common scenario is the derivation of new values from answers, e.g.
computing the slug of a human-readable name:

```yaml title="copier.yml"
_exclude:
    - name-slug

name:
    type: str
    help: A nice human-readable name

slug:
    type: str
    help: A slug of the name
    default: "{% include 'name-slug.jinja' %}"
```

```jinja title="name-slug.jinja"
{# For simplicity ... -#}
{{ name|lower|replace(' ', '-') }}
```

```tree result="shell"
your_template
    copier.yml
    name-slug.jinja
```

It is also possible to include a template in a templated folder name

```tree result="shell"
your_template
    copier.yml
    name-slug.jinja
    {% include 'name-slug.jinja' %}
        __init__.py
```

or in a templated file name

```tree result="shell"
your_template
    copier.yml
    name-slug.jinja
    {% include 'name-slug.jinja' %}.py
```

or in the templated content of a text file:

```toml title="pyproject.toml.jinja"
[project]
name = "{% include 'name-slug.jinja' %}"
# ...
```

Similarly, a Jinja macro can be defined

```jinja title="slugify.jinja"
{# For simplicity ... -#}
{% macro slugify(value) -%}
{{ value|lower|replace(' ', '-') }}
{%- endmacro %}
```

and imported, e.g. in `copier.yml`

```yaml title="copier.yml"
_exclude:
    - slugify

name:
    type: str
    help: A nice human-readable name

slug:
    type: str
    help: A slug of the name
    default: "{% from 'slugify.jinja' import slugify %}{{ slugify(name) }}"
```

or in a templated folder name, in a templated file name, or in the templated content of
a text file.

!!! info

    Import/Include paths are relative to the template root.

As the number of imported templates and macros grows, you may want to place them in a
dedicated folder such as `includes`:

```tree result="shell"
your_template
    copier.yml
    includes
        name-slug.jinja
        slugify.jinja
        ...
```

Then, make sure to [exclude][exclude] this folder

```yaml title="copier.yml"
_exclude:
    - includes
```

or use a [subdirectory][subdirectory], e.g.:

```yaml title="copier.yml"
_subdirectory: template
```

In addition, Jinja include and import statements will need to use a POSIX path separator
(also on Windows) which is not supported in templated folder and file names. For this
reason, Copier provides a function
`pathjoin(*paths: str, mode: Literal["posix", "windows", "native"] = "posix")`:

```jinja
{% include pathjoin('includes', 'name-slug.jinja') %}
```

```jinja
{% from pathjoin('includes', 'slugify.jinja') import slugify %}
```

## Available settings

Template settings alter how the template is rendered. [They come from several
sources][configuration-sources].

Remember that **the key must be prefixed with an underscore if you use it in [the
`copier.yml` file][the-copieryml-file]**.

### `answers_file`

-   Format: `str`
-   CLI flags: `-a`, `--answers-file`
-   Default value: `.copier-answers.yml`

Path to a file where answers will be recorded by default. The path must be relative to
the project root.

!!! tip

    Remember to add that file to your Git template if you want to support
    [updates](updating.md).

Don't forget to read [the docs about the answers file][the-copier-answersyml-file].

!!! example

    ```yaml title="copier.yml"
    _answers_file: .my-custom-answers.yml
    ```

### `cleanup_on_error`

-   Format: `bool`
-   CLI flags: `-C`, `--no-cleanup` (used to disable this setting; only available in
    `copier copy` subcommand)
-   Default value: `True`

When Copier creates the destination path, if there's any failure when rendering the
template (either in the rendering process or when running the [tasks][tasks]), Copier
will delete that folder.

Copier will never delete the folder if it didn't create it. For this reason, when
running `copier update`, this setting has no effect.

!!! info

    Not supported in `copier.yml`.

### `conflict`

-   Format: `Literal["rej", "inline"]`
-   CLI flags: `-o`, `--conflict` (only available in `copier update` subcommand)
-   Default value: `inline`

When updating a project, sometimes Copier doesn't know what to do with a diff code hunk.
This option controls the output format if this happens. Using `rej`, creates `*.rej`
files that contain the unresolved diffs. The `inline` option (default) includes the diff
code hunk in the file itself, similar to the behavior of `git merge`.

!!! info

    Not supported in `copier.yml`.

### `context_lines`

-   Format: `Int`
-   CLI flags: `-c`, `--context-lines` (only available in `copier update` subcommand)
-   Default value: `1`

During a project update, Copier needs to compare the template evolution with the
subproject evolution. This way, it can detect what changed, where and how to merge those
changes. [Refer here for more details on this process](updating.md).

The more lines you use, the more accurate Copier will be when detecting conflicts. But
you will also have more conflicts to solve by yourself. FWIW, Git uses 3 lines by
default.

The less lines you use, the less conflicts you will have. However, Copier will not be so
accurate and could even move lines around if the file it's comparing has several similar
code chunks.

!!! info

    Not supported in `copier.yml`.

### `data`

-   Format: `dict|List[str=str]`
-   CLI flags: `-d`, `--data`
-   Default value: N/A

Give answers to questions through CLI/API.

This cannot be defined in `copier.yml`, where its equivalent would be just normal
questions with default answers.

!!! example

    Example CLI usage to take all default answers from template, except the user name,
    which is overridden, and don't ask user anything else:

    ```shell
    copier copy -fd 'user_name=Manuel Calavera' template destination
    ```

### `data_file`

-   Format: `str`
-   CLI flags: `--data-file`
-   Default value: N/A

As an alternative to [`-d, --data`][data] you can also pass the path to a YAML file that
contains your data.

!!! info

    Not supported in `copier.yml` or API calls. Only supported through the CLI.

!!! example

    Example CLI usage with a YAML file containing data:

    ```yaml title="input.yml"
    user_name: Manuel Calavera
    age: 7
    height: 1.83
    ```

    Passing a data file

    ```shell
    copier copy --data-file input.yml template destination
    ```

    is equivalent to passing its content as key-value pairs:

    ```shell
    copier copy -d 'user_name=Manuel Calavera' -d 'age=7' -d 'height=1.83' template destination
    ```

    If you'd like to override some of the answers in the file, `--data` flags always take
    precedence:

    ```shell
    copier copy -d 'user_name=Bilbo Baggins' --data-file input.yml template destination
    ```

!!! info

    Command line arguments passed via `--data` always take precedence over the data file.

### `envops`

-   Format: `dict`
-   CLI flags: N/A
-   Default value: `{"keep_trailing_newline": true}`

Configurations for the Jinja environment. Copier uses the Jinja defaults whenever
possible. The only exception at the moment is that
[Copier keeps trailing newlines](https://github.com/copier-org/copier/issues/464) at the
end of a template file. If you want to remove those, either remove them from the
template or set `keep_trailing_newline` to `false`.

See [upstream docs](https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment)
to know available options.

!!! warning

    Copier 5 and older had different, bracket-based defaults.

    If your template was created for Copier 5, you need to add this configuration to
    your `copier.yaml` to keep it working just like before:

    ```yaml
    _envops:
        autoescape: false
        block_end_string: "%]"
        block_start_string: "[%"
        comment_end_string: "#]"
        comment_start_string: "[#"
        keep_trailing_newline: true
        variable_end_string: "]]"
        variable_start_string: "[["
    ```

    By specifying this, your template will be compatible with both Copier 5 and 6.

    Copier 6 will apply these older defaults if your [min_copier_version][] is lower
    than 6.

    Copier 7+ no longer uses the old defaults independent of [min_copier_version][].

### `exclude`

-   Format: `List[str]`
-   CLI flags: `-x`, `--exclude`
-   Default value:
    `["copier.yaml", "copier.yml", "~*", "*.py[co]", "__pycache__", ".git", ".DS_Store", ".svn"]`

[Patterns][patterns-syntax] for files/folders that must not be copied.

The CLI option can be passed several times to add several patterns.

!!! info

    When you define this parameter in `copier.yml`, it will **replace** the default
    value.

    In this example, for instance, `"copier.yml"` will **not** be excluded:

    !!! example

        ```yaml
        _exclude:
            - "*.bar"
            - ".git"
        ```

!!! info

    When the [`subdirectory`][subdirectory] parameter is defined and its value is the
    path of an actual subdirectory (i.e. not `""` or `"."` or `"./"`), then the default
    value of the `exclude` parameter is `[]`.

!!! info

    When you add this parameter from CLI or API, it will **not replace** the values
    defined in `copier.yml` (or the defaults, if missing).

    Instead, CLI/API definitions **will extend** those from `copier.yml`.


    !!! example "Example CLI usage to copy only a single file from the template"

        ```shell
        copier copy --exclude '*' --exclude '!file-i-want' ./template ./destination
        ```

### `force`

-   Format: `bool`
-   CLI flags: `-f`, `--force` (N/A in `copier update`)
-   Default value: `False`

Overwrite files that already exist, without asking.

Also don't ask questions to the user; just use default values [obtained from other
sources][configuration-sources].

!!! info

    Not supported in `copier.yml`.

### `defaults`

-   Format: `bool`
-   CLI flags: `--defaults`
-   Default value: `False`

Use default answers to questions.

!!! attention

    Any question that does not have a default value must be answered
    [via CLI/API][data]. Otherwise, an error is raised.

!!! info

    Not supported in `copier.yml`.

### `overwrite`

-   Format: `bool`
-   CLI flags: `--overwrite` (N/A in `copier update` because it's implicit)
-   Default value: `False`

Overwrite files that already exist, without asking.

[obtained from other sources][configuration-sources].

!!! info

    Not supported in `copier.yml`.

    Required when updating from API.

### `jinja_extensions`

-   Format: `List[str]`
-   CLI flags: N/A
-   Default value: `[]`

Additional Jinja2 extensions to load in the Jinja2 environment. Extensions can add
filters, global variables and functions, or tags to the environment.

The following extensions are _always_ loaded:

-   [`jinja2_ansible_filters.AnsibleCoreFiltersExtension`](https://gitlab.com/dreamer-labs/libraries/jinja2-ansible-filters/):
    this extension adds most of the
    [Ansible filters](https://docs.ansible.com/ansible/2.3/playbooks_filters.html) to
    the environment.

You don't need to tell your template users to install these extensions: Copier depends
on them, so they are always installed when Copier is installed.

!!! warning

    Including an extension allows Copier to execute uncontrolled code, thus making the
    template potentially more dangerous. Be careful about what extensions you install.

!!! info "Note to template writers"

    You must inform your users that they need to install the extensions alongside Copier,
    i.e. in the same virtualenv where Copier is installed.
    For example, if your template uses `jinja2_time.TimeExtension`,
    your users must install the `jinja2-time` Python package.

    ```shell
    # with pip, in the same virtualenv where Copier is installed
    pip install jinja2-time

    # if Copier was installed with pipx
    pipx inject copier jinja2-time
    # if Copier was installed with uv
    uv tool install --with jinja2-time copier
    ```

!!! example

    ```yaml title="copier.yml"
    _jinja_extensions:
        - jinja_markdown.MarkdownExtension
        - jinja2_slug.SlugExtension
        - jinja2_time.TimeExtension
    ```

!!! hint

    Examples of extensions you can use:

    -   [Native Jinja2 extensions](https://jinja.palletsprojects.com/en/3.1.x/extensions/):
        -   [expression statement](https://jinja.palletsprojects.com/en/3.1.x/templates/#expression-statement),
            which can be used to alter the Jinja context (answers, filters, etc.) or execute other operations, without outputting anything.
        -   [loop controls](https://jinja.palletsprojects.com/en/3.1.x/extensions/#loop-controls), which adds the `break` and `continue`
            keywords for Jinja loops.
        -   [debug extension](https://jinja.palletsprojects.com/en/3.1.x/extensions/#debug-extension), which can dump the current context
            thanks to the added `{% debug %}` tag.

    -   From [cookiecutter](https://cookiecutter.readthedocs.io/en/1.7.2/):

        -   [`cookiecutter.extensions.JsonifyExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#jsonify-extension):
            provides a `jsonify` filter, to format a dictionary as JSON. Note that Copier
            natively provides a `to_nice_json` filter that can achieve the same thing.
        -   [`cookiecutter.extensions.RandomStringExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#random-string-extension):
            provides a `random_ascii_string(length, punctuation=False)` global function.
            Note that Copier natively provides the `ans_random` and `hash` filters that can
            be used to achieve the same thing:

            !!! example

                ```jinja
                {{ 999999999999999999999999999999999|ans_random|hash('sha512') }}
                ```

        -   [`cookiecutter.extensions.SlugifyExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#slugify-extension):
            provides a `slugify` filter using
            [python-slugify](https://github.com/un33k/python-slugify).

    -   [`copier_templates_extensions.TemplateExtensionLoader`](https://github.com/copier-org/copier-templates-extensions):
        enhances the extension loading mechanism to allow templates writers to put their
        extensions directly in their templates. It also allows to modify the rendering context
        (the Jinja variables that you can use in your templates) before
        rendering templates, see [using a context hook][how-can-i-alter-the-context-before-rendering-the-project].
    -   [`jinja_markdown.MarkdownExtension`](https://github.com/jpsca/jinja-markdown):
        provides a `markdown` tag that will render Markdown to HTML using
        [PyMdown extensions](https://facelessuser.github.io/pymdown-extensions/).
    -   [`jinja2_slug.SlugExtension`](https://pypi.org/project/jinja2-slug/#files): provides
        a `slug` filter using [unicode-slugify](https://github.com/mozilla/unicode-slugify).
    -   [`jinja2_time.TimeExtension`](https://github.com/hackebrot/jinja2-time): adds a
        `now` tag that provides convenient access to the
        [arrow.now()](http://crsmithdev.com/arrow/#arrow.factory.ArrowFactory.now) API.
    -   [`jinja2_jsonschema.JsonSchemaExtension`](https://github.com/copier-org/jinja2-jsonschema):
        adds a `jsonschema` filter for validating data against a JSON/YAML schema.

    Search for more extensions on GitHub using the
    [jinja2-extension topic](https://github.com/topics/jinja2-extension), or
    [other Jinja2 topics](https://github.com/search?q=jinja&type=topics), or
    [on PyPI using the jinja + extension keywords](https://pypi.org/search/?q=jinja+extension).

### `message_after_copy`

-   Format: `str`
-   CLI flags: N/A
-   Default value: `""`

A message to be printed after [generating](generating.md) or
[regenerating][regenerating-a-project] a project _successfully_.

If the message contains Jinja code, it will be rendered with the same context as the
rest of the template. A [Jinja include][importing-jinja-templates-and-macros] expression
may be used to import a message from a file.

The message is suppressed when Copier is run in [quiet mode][quiet].

!!! example

    ```yaml title="copier.yml"
    project_name:
        type: str
        help: An awesome project needs an awesome name. Tell me yours.

    _message_after_copy: |
        Your project "{{ project_name }}" has been created successfully!

        Next steps:

        1. Change directory to the project root:

           $ cd {{ _copier_conf.dst_path }}

        2. Read "CONTRIBUING.md" and start coding.
    ```

### `message_after_update`

-   Format: `str`
-   CLI flags: N/A
-   Default value: `""`

Like [`message_after_copy`][message_after_copy] but printed after
[_updating_](updating.md) a project.

!!! example

    ```yaml title="copier.yml"
    project_name:
        type: str
        help: An awesome project needs an awesome name. Tell me yours.

    _message_after_update: |
        Your project "{{ project_name }}" has been updated successfully!
        In case there are any conflicts, please resolve them. Then,
        you're done.
    ```

### `message_before_copy`

-   Format: `str`
-   CLI flags: N/A
-   Default value: `""`

Like [`message_after_copy`][message_after_copy] but printed _before_
[generating](generating.md) or [regenerating][regenerating-a-project] a project.

!!! example

    ```yaml title="copier.yml"
    project_name:
        type: str
        help: An awesome project needs an awesome name. Tell me yours.

    _message_before_copy: |
        Thanks for generating a project using our template.

        You'll be asked a series of questions whose answers will be used to
        generate a tailored project for you.
    ```

### `message_before_update`

-   Format: `str`
-   CLI flags: N/A
-   Default value: `""`

Like [`message_before_copy`][message_after_copy] but printed before
[_updating_](updating.md) a project.

!!! example

    ```yaml title="copier.yml"
    project_name:
        type: str
        help: An awesome project needs an awesome name. Tell me yours.

    _message_before_update: |
        Thanks for updating your project using our template.

        You'll be asked a series of questions whose answers are pre-populated
        with previously entered values. Feel free to change them as needed.
    ```

### `migrations`

-   Format: `List[str|List[str]|dict]`
-   CLI flags: N/A
-   Default value: `[]`

Migrations are like [tasks][tasks], but each item can have additional keys:

-   **command**: The migration command to run
-   **version** (optional): Indicates the version that the template update has to go
    through to trigger this migration. It is evaluated using [PEP 440][]. If no version
    is specified the migration will run on every update.
-   **when** (optional): Specifies a condition that needs to hold for the task to run.
    By default, a migration will run in the after upgrade stage.
-   **working_directory** (optional): Specifies the directory in which the command will
    be run. Defaults to the destination directory.

If a `str` or `List[str]` is given as a migrator it will be treated as `command` with
all other items not present.

Migrations will run in the same order as declared here (so you could even run a
migration for a higher version before running a migration for a lower version if the
higher one is declared before and the update passes through both).

When `version` is given they will only run when _new version >= declared version > old
version_. Your template will only be marked as [unsafe][unsafe] if this condition is
true. Migrations will also only run when updating (not when copying for the 1st time).

If the migrations definition contains Jinja code, it will be rendered with the same
context as the rest of the template.

There are a number of additional variables available for templating of migrations. Those
variables are also passed to the migration process as environment variables. Migration
processes will receive these variables:

-   `_stage`/`$STAGE`: Either `before` or `after`.
-   `_version_from`/`$VERSION_FROM`: [Git commit description][git describe] of the
    template as it was before updating.
-   `_version_to`/`$VERSION_TO`: [Git commit description][git describe] of the template
    as it will be after updating.
-   `_version_current`/`$VERSION_CURRENT`: The `version` detector as you indicated it
    when describing migration tasks (only when `version` is given).
-   `_version_pep440_from`/`$VERSION_PEP440_FROM`,
    `_version_pep440_to`/`$VERSION_PEP440_TO`,
    `_version_pep440_current`/`$VERSION_PEP440_CURRENT`: Same as the above, but
    normalized into a standard [PEP 440][] version. In Jinja templates these are
    represented as
    [packaging.version.Version](https://packaging.pypa.io/en/stable/version.html#packaging.version.Version)
    objects and allow access to their attributes. As environment variables they are
    represented as strings. If you use variables to perform migrations, you probably
    will prefer to use these variables.

[git describe]: https://git-scm.com/docs/git-describe
[pep 440]: https://www.python.org/dev/peps/pep-0440/

!!! example

    ```yaml title="copier.yml"
    _migrations:
      # {{ _copier_conf.src_path }} points to the path where the template was
      # cloned, so it can be helpful to run migration scripts stored there.
      - invoke -r {{ _copier_conf.src_path }} -c migrations migrate $STAGE $VERSION_FROM $VERSION_TO
      - version: v1.0.0
        command: rm ./old-folder
        when: "{{ _stage == 'before' }}"
    ```

In Copier versions before v9.3.0 a different configuration format had to be used. This
format is still available, but will raise a warning when used.

Each item in the list is a `dict` with the following keys:

-   **version**: Indicates the version that the template update has to go through to
    trigger this migration. It is evaluated using [PEP 440][].
-   **before** (optional): Commands to execute before performing the update. The answers
    file is reloaded after running migrations in this stage, to let you migrate answer
    values.
-   **after** (optional): Commands to execute after performing the update.

The migration variables mentioned above are available as environment variables, but
can't be used in jinja templates.

### `min_copier_version`

-   Format: `str`
-   CLI flags: N/A
-   Default value: N/A

Specifies the minimum required version of Copier to generate a project from this
template. The version must be follow the [PEP 440][] syntax. Upon generating or updating
a project, if the installed version of Copier is less than the required one, the
generation will be aborted and an error will be shown to the user.

!!! info

    If Copier detects that there is a major version difference, it will warn you about
    possible incompatibilities. Remember that a new major release means that some
    features can be dropped or changed, so it's probably a good idea to ask the
    template maintainer to update it.

!!! example

    ```yaml title="copier.yml"
    _min_copier_version: "4.1.0"
    ```

### `pretend`

-   Format: `bool`
-   CLI flags: `-n`, `--pretend`
-   Default value: `False`

Run but do not make any changes.

!!! info

    Not supported in `copier.yml`.

### `preserve_symlinks`

-   Format: `bool`
-   CLI flags: N/A
-   Default value: `False`

Keep symlinks as symlinks. If this is set to `False` symlinks will be replaced with the
file they point to.

When set to `True` and the symlink ends with the template suffix (`.jinja` by default)
the target path of the symlink will be rendered as a jinja template.

### `quiet`

-   Format: `bool`
-   CLI flags: `-q`, `--quiet`
-   Default value: `False`

Suppress status output.

!!! info

    Not supported in `copier.yml`.

### `secret_questions`

-   Format: `List[str]`
-   CLI flags: N/A
-   Default value: `[]`

Question variables to mark as secret questions. This is especially useful when questions
are provided in the [simplified prompt format][questions]. It's equivalent to
configuring `secret: true` in the [advanced prompt format][advanced-prompt-formatting].

!!! example

    ```yaml title="copier.yml"
    _secret_questions:
        - password

    user: johndoe
    password: s3cr3t
    ```

### `skip_if_exists`

-   Format: `List[str]`
-   CLI flags: `-s`, `--skip`
-   Default value: `[]`

[Patterns][patterns-syntax] for files/folders that must be skipped only if they already
exist, but always be present. If they do not exist in a project during an `update`
operation, they will be recreated.

!!! example

    For example, it can be used if your project generates a password the 1st time and
    you don't want to override it next times:

    ```yaml title="copier.yml"
    _skip_if_exists:
        - .secret_password.yml
    ```

    ```yaml title=".secret_password.yml.jinja"
    {{999999999999999999999999999999999|ans_random|hash('sha512')}}
    ```

### `skip_tasks`

-   Format: `bool`
-   CLI Flags: `-T`, `--skip-tasks`
-   Default value: `False`

Skip template [tasks][tasks] execution, if set to `True`.

!!! note

    It only skips [tasks][tasks], not [migration tasks][migrations].

!!! question "Does it imply `--trust`?"

    This flag does not imply [`--trust`][unsafe], and will do nothing if not used with.

### `subdirectory`

-   Format: `str`
-   CLI flags: N/A
-   Default value: N/A

Subdirectory to use as the template root when generating a project. If not specified,
the root of the template is used.

This allows you to keep separate the template metadata and the template code.

!!! tip

    If your template is meant to be applied to other templates (a.k.a. recursive
    templates), use this option to be able to use [updates](updating.md).

!!! example

    ```yaml title="copier.yml"
    _subdirectory: template
    ```

!!! question "Can I have multiple templates in a single repo using this option?"

    The Copier recommendation is: **1 template = 1 Git repository**.

    Why? Unlike almost all other templating engines, Copier supports
    [smart project updates](updating.md). For that, Copier needs to know in which version it
    was copied last time, and to which version you are evolving. Copier gets that
    information from Git tags. Git tags are shared across the whole Git repository. Using a
    repository to host multiple templates would lead to many corner case situations that we
    don't want to support.

    So, in Copier, the subdirectory option is just there to let template owners separate
    templates metadata from template source code. This way, for example, you can have
    different dotfiles for you template and for the projects it generates.

    !!! example "Example project with different `.gitignore` files"


        ```tree result="shell" title="Project layout"
        my_copier_template
            copier.yml       # (1)
            .gitignore       # (2)
            template         # (3)
                .gitignore   # (4)
        ```

        1.  Same contents as the example above.
        1.  Ignore instructions for the template repo.
        1.  The configured template subdirectory.
        1.  Ignore instructions for projects generated with the template.

    However, it is true that the value of this option can itself be templated. This would
    let you have different templates that all use the same questionnaire, and the used
    template would be saved as an answer. It would let the user update safely and change
    that option in the future.

    !!! example

        With this questions file and this directory structure, the user will be prompted which
        Python engine to use, and the project will be generated using the subdirectory whose
        name matches the answer from the user:

        ```yaml title="copier.yaml"
        _subdirectory: "{{ python_engine }}"
        python_engine:
            type: str
            choices:
                - poetry
                - pipenv
        ```

        ```tree result="shell" title="Project layout"
        my_copier_template
            copier.yaml # (1)
            poetry
                {{ _copier_conf.answers_file }}.jinja # (2)
                pyproject.toml.jinja
            pipenv
                {{ _copier_conf.answers_file }}.jinja
                Pipfile.jinja
        ```

        1.  The configuration from the previous example snippet.
        1.  See [the answers file docs][the-copier-answersyml-file] to understand.

### `tasks`

-   Format: `List[str|List[str]|dict]`
-   CLI flags: N/A
-   Default value: `[]`

Commands to execute after generating or updating a project from your template.

They run ordered, and with the `$STAGE=task` variable in their environment.

If a `dict` is given it can contain the following items:

-   **command**: The task command to run.
-   **when** (optional): Specifies a condition that needs to hold for the task to run.
-   **working_directory** (optional): Specifies the directory in which the command will
    be run. Defaults to the destination directory.

If a `str` or `List[str]` is given as a task it will be treated as `command` with all
other items not present.

!!! example

    ```yaml title="copier.yml"
    _tasks:
        # Strings get executed under system's default shell
        - "git init"
        - "rm {{ name_of_the_project }}/README.md"
        # Arrays are executed without shell, saving you the work of escaping arguments
        - [invoke, "--search-root={{ _copier_conf.src_path }}", after-copy]
        # You are able to output the full conf to JSON, to be parsed by your script
        - [invoke, end-process, "--full-conf={{ _copier_conf|to_json }}"]
        # Your script can be run by the same Python environment used to run Copier
        - ["{{ _copier_python }}", task.py]
        # OS-specific task (supported values are "linux", "macos", "windows" and `None`)
        - command: rm {{ name_of_the_project }}/README.md
          when: "{{ _copier_conf.os in  ['linux', 'macos'] }}"
        - command: Remove-Item {{ name_of_the_project }}\\README.md
          when: "{{ _copier_conf.os == 'windows' }}"
    ```

    Note: the example assumes you use [Invoke](https://www.pyinvoke.org/) as
    your task manager. But it's just an example. The point is that we're showing
    how to build and call commands.

### `templates_suffix`

-   Format: `str`
-   CLI flags: N/A
-   Default value: `.jinja`

Suffix that instructs which files are to be processed by Jinja as templates.

!!! example

    ```yaml title="copier.yml"
    _templates_suffix: .my-custom-suffix
    ```

An empty suffix is also valid, and will instruct Copier to copy and render _every file_,
except those that are [excluded by default][exclude]. If an error happens while trying
to read a file as a template, it will fallback to a simple copy (it will typically
happen for binary files like images). At the contrary, if such an error happens and the
templates suffix is _not_ empty, Copier will abort and print an error message.

!!! example

    ```yaml title="copier.yml"
    _templates_suffix: ""
    ```

If there is a file with the template suffix next to another one without it, the one
without suffix will be ignored.

!!! example

    ```tree result="shell"
    my_copier_template
        README.md           # Your template's README, ignored at rendering
        README.md.jinja     # README that will be rendered
        CONTRIBUTING.md     # Used both for the template and the subprojects
    ```

!!! warning

    Copier 5 and older had a different default value: `.tmpl`. If you wish to keep it,
    add it to your `copier.yml` to keep it future-proof.

    Copier 6 will apply that old default if your [min_copier_version][] is lower
    than 6.

    Copier 7+ no longer uses the old default independent of [min_copier_version][].

### `unsafe`

-   Format: `bool`
-   CLI flags: `--UNSAFE`, `--trust`
-   Default value: `False`

Copier templates can use dangerous features that allow arbitrary code execution:

-   [Jinja extensions][jinja_extensions]
-   [Migrations][migrations]
-   [Tasks][tasks]

Therefore, these features are disabled by default and Copier will raise an error (and
exit from the CLI with code `4`) when they are found in a template. In this case, please
verify that no malicious code gets executed by any of the used features. When you're
sufficiently confident or willing to take the risk, set `unsafe=True` or pass the CLI
switch `--UNSAFE` or `--trust`.

!!! danger

    Please be sure you understand the risks when allowing unsafe features!

!!! info

    Not supported in `copier.yml`.

!!! tip

    See the [`trust` setting][trusted-locations] to mark some repositories as always trusted.

### `use_prereleases`

-   Format: `bool`
-   CLI flags: `g`, `--prereleases`
-   Default value: `False`

Imagine that the template supports updates and contains these 2 Git tags: `v1.0.0` and
`v2.0.0a1`. Copier will copy by default `v1.0.0` unless you add `--prereleases`.

<!-- prettier-ignore-start -->
Also, if you run [`copier update`][copier.cli.CopierUpdateSubApp], Copier would ignore
the `v2.0.0a1` tag unless this flag is enabled.
<!-- prettier-ignore-end -->

!!! warning

    This behavior is new from Copier 5.0.0. Before that release, prereleases were
    never ignored.

!!! info

    Not supported in `copier.yml`.

### `vcs_ref`

-   Format: `str`
-   CLI flags: `-r`, `--vcs-ref`
-   Default value: N/A (use latest release)

When copying or updating from a Git-versioned template, indicate which template version
to copy.

This is stored automatically in the answers file, like this:

```yaml
_commit: v1.0.0
```

!!! info

    Not supported in `copier.yml`.

By default, Copier will copy from the last release found in template Git tags, sorted as
[PEP 440][].

## Patterns syntax

Copier supports matching names against patterns in a gitignore style fashion. This works
for the options `exclude` and `skip`. This means you can write patterns as you would for
any `.gitignore` file. The full range of the gitignore syntax is supported via
[pathspec](https://github.com/cpburnz/python-path-specification).

For example, with the following settings in your `copier.yml` file would exclude all
files ending with `txt` from being copied to the destination folder, except the file
`a.txt`.

```yaml
_exclude:
    # match all text files...
    - "*.txt"
    # .. but not this one:
    - "!a.txt"
```

## The `.copier-answers.yml` file

If the destination path exists and a `.copier-answers.yml` file is present there, it
will be used to load the last user's answers to the questions made in [the `copier.yml`
file][the-copieryml-file].

This makes projects easier to update because when the user is asked, the default answers
will be the last ones they used.

The file **must be called exactly `{{ _copier_conf.answers_file }}.jinja`** (or ended
with [your chosen suffix][templates_suffix]) in your template's root folder) to allow
[applying multiple templates to the same
subproject][applying-multiple-templates-to-the-same-subproject].

The default name will be `.copier-answers.yml`, but [you can define a different default
path for this file][answers_file].

The file must have this content:

```yaml+jinja
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
{{ _copier_answers|to_nice_yaml -}}
```

!!! important

    Did you notice that `NEVER EDIT MANUALLY` part?
    [It is important][never-change-the-answers-file-manually].

The builtin `_copier_answers` variable includes all data needed to smooth future updates
of this project. This includes (but is not limited to) all JSON-serializable values
declared as user questions in [the `copier.yml` file][the-copieryml-file].

As you can see, you also have the power to customize what will be logged here. Keys that
start with an underscore (`_`) are specific to Copier. Other keys should match questions
in `copier.yml`.

The path to the answers file must be expressed relative to the project root, because:

-   Its value must be available at render time.
-   It is used to update projects, and for that a project must be git-tracked. So, the
    file must be in the repo anyway.

### Applying multiple templates to the same subproject

Imagine this scenario:

1. You use one framework that has a public template to generate a project. It's
   available at `https://github.com/example-framework/framework-template.git`.
1. You have a generic template that you apply to all your projects to use the same
   pre-commit configuration (formatters, linters, static type checkers...). You have
   published that in `https://gitlab.com/my-stuff/pre-commit-template.git`.
1. You have a private template that configures your subproject to run in your internal
   CI. It's found in `git@gitlab.example.com:my-company/ci-template.git`.

All 3 templates are completely independent:

-   Anybody can generate a project for the specific framework, no matter if they want to
    use pre-commit or not.
-   You want to share the same pre-commit configurations, no matter if the subproject is
    for one or another framework.
-   You want to have a centralized CI configuration for all your company projects, no
    matter their pre-commit configuration or the framework they rely on.

Well, don't worry. Copier has you covered. You just need to use a different answers file
for each one. All of them contain a `{{ _copier_conf.answers_file }}.jinja` file [as
specified above][the-copier-answersyml-file]. Then you apply all the templates to the
same project:

```shell
mkdir my-project
cd my-project
git init
# Apply framework template
copier copy -a .copier-answers.main.yml https://github.com/example-framework/framework-template.git .
git add .
git commit -m 'Start project based on framework template'
# Apply pre-commit template
copier copy -a .copier-answers.pre-commit.yml https://gitlab.com/my-stuff/pre-commit-template.git .
git add .
pre-commit run -a  # Just in case 😉
git commit -am 'Apply pre-commit template'
# Apply internal CI template
copier copy -a .copier-answers.ci.yml git@gitlab.example.com:my-company/ci-template.git .
git add .
git commit -m 'Apply internal CI template'
```

Done!

After a while, when templates get new releases, updates are handled separately for each
template:

```shell
copier update -a .copier-answers.main.yml
copier update -a .copier-answers.pre-commit.yml
copier update -a .copier-answers.ci.yml
```
