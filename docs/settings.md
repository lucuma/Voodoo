# Settings

Copier settings are stored in `<CONFIG_ROOT>/settings.yml` where `<CONFIG_ROOT>` is the
standard configuration directory for your platform:

-   `$XDG_CONFIG_HOME/copier` (`~/.config/copier ` in most cases) on Linux as defined by
    [XDG Base Directory Specifications](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
-   `~/Library/Application Support/copier` on macOS as defined by
    [Apple File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
-   `%USERPROFILE%\AppData\Local\copier` on Windows as defined in
    [Known folders](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders)

This location can be overridden by setting the `COPIER_SETTINGS_PATH` environment
variable.

## User defaults

Users may define some reusable default variables in the `defaults` section of the
configuration file.

```yaml title="<CONFIG_ROOT>/settings.yml"
defaults:
    user_name: "John Doe"
    user_email: john.doe@acme.com
```

This user data will replace the default value of fields of the same name.

### Well-known variables

To ensure templates efficiently reuse user-defined variables, we invite template authors
to use the following well-known variables:

| Variable name | Type  | Description            |
| ------------- | ----- | ---------------------- |
| `user_name`   | `str` | User's full name       |
| `user_email`  | `str` | User's email address   |
| `github_user` | `str` | User's GitHub username |
| `gitlab_user` | `str` | User's GitLab username |

## Trusted locations

Users may define trusted locations in the `trust` setting. It should be a list of Copier
template repositories, or repositories prefix.

```yaml
trust:
    - https://github.com/your_account/your_template.git
    - https://github.com/your_account/
    - ~/templates/
```

!!! warning "Security considerations"

    Locations ending with `/` will be matched as prefixes, trusting all templates starting with that path.
    Locations not ending with `/` will be matched exactly.

## Shortcuts

It is possible to define shortcuts in the `shortcuts` setting. It should be a dictionary
where keys are the shortcut names and values are [copier.settings.Shortcut][] objects.

```yaml
shortcuts:
    company:
        url: "https://git.company.org"
        suffix: true
    local:
        url: ~/project/templates
        suffix: false
```

If suffix is `True` (default), the `.git` suffix will be appended to the URL if missing.

A string can be used as short syntax instead of a full Shortcut object.

This snippet is equivalent to the previous one:

```yaml
shortcuts:
    company: "https://git.company.org"
    local:
        url: ~/project/templates
        suffix: false
```

You can now write:

```shell
copier copy company:team/repo
copier copy local:template
```

There are 2 default shortcuts always available unless you explicitely override them:

```yaml
shortcuts:
    gh: "https://github.com/"
    gl: "https://gitlab.com/"
```

!!! tip "Working with private repositories"

    If you work with private GitHub or Gitlab repositories,
    you might want to override those to force authenticated ssh access:

    ```yaml
    shortcuts:
        gh: 'git@github.com:'
        gl: 'git@gitlab.com:'
    ```

    Note the trailing `:` in the URL, it is required to make Git use the SSH protocol.
    (`gh:user/repo` will be expanded into `git@github.com:user/repo.git`)

!!! tip "Trusted locations and shortcuts"

    Trusted locations can be defined using shortcuts.

    ```yaml
    trust:
        - gh:user/repo
        - gh:company/
        - 'local:'
    ```
