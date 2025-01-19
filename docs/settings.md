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
