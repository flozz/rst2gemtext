import nox


PYTHON_FILES = [
    "rst2gemtext.py",
    "noxfile.py",
    "tests",
]


@nox.session(reuse_venv=True)
def lint(session):
    session.install("-e", ".[dev]")
    session.run("flake8", *PYTHON_FILES)
    session.run("black", "--check", "--diff", "--color", *PYTHON_FILES)
    session.run("validate-pyproject", "pyproject.toml")


@nox.session(reuse_venv=True)
def black_fix(session):
    session.install("black")
    session.run("black", *PYTHON_FILES)


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13"], reuse_venv=True)
def test(session):
    session.install("pytest")
    session.install("-e", ".")
    session.run("pytest", "-vv", "--doctest-modules", "rst2gemtext.py", "tests/")
