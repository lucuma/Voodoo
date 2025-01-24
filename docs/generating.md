# Generating a project

!!! warning

    Generate projects only from trusted templates as their tasks run with the
    same level of access as your user.

As seen in the quick usage section, you can generate a project from a template using the
`copier` command-line tool:

```shell
copier copy path/to/project/template path/to/destination
```

Or within Python code:

```python
copier.run_copy("path/to/project/template", "path/to/destination")
```

If `path/to/destination` doesn't exist, Copier will create the directory and populate it
with the generated files. If `path/to/destination` exists, it must be writable (not
read-only).

The "template" parameter can be a local path, an URL, or a shortcut URL:

-   GitHub: `gh:namespace/project`
-   GitLab: `gl:namespace/project`

If Copier doesn't detect your remote URL as a Git repository, make sure it starts with
one of `git+https://`, `git+ssh://`, `git@` or `git://`, or it ends with `.git`.

Use the `--data` command-line argument or the `data` parameter of the
`copier.run_copy()` function to pass whatever extra context you want to be available in
the templates. The arguments can be any valid Python value, even a function.

Use the `--vcs-ref` command-line argument to checkout a particular Git ref before
generating the project.

[All the available options][copier.cli] are described with the `--help-all` option.

## Templates versions

By default, Copier will copy from the last release found in template Git tags, sorted as
[PEP 440](https://peps.python.org/pep-0440/), regardless of whether the template is from
a URL or a local clone of a Git repository.

### Copying dirty changes

If you use a local clone of a template repository that has had any uncommitted
modifications made, Copier will use this modified working copy of the template to aid
development of new template features.

If you would like to override the version of template being installed, the
[`--vcs-ref`][vcs_ref] argument can be used to specify a branch, tag or other reference
to use.

For example to use the latest master branch from a public repository:

```shell
copier copy --vcs-ref master https://github.com/foo/copier-template.git ./path/to/destination
```

Or to work from the current checked out revision of a local template (including dirty
changes):

```shell
copier copy --vcs-ref HEAD path/to/project/template path/to/destination
```

## Regenerating a project

When you execute `copier recopy $project` again over a preexisting `$project`, Copier
will just reapply the template on it, keeping answers but ignoring previous history.

!!! warning

    This is not [the recommended approach for updating a project][updating-a-project],
    where you usually want Copier to respect the project evolution wherever it doesn't
    conflict with the template evolution.
