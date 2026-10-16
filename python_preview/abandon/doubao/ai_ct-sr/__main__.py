"""Command-line interface."""
import click


@click.command()
@click.version_option()
def main() -> None:
    """CT-SR command-line interface."""


if __name__ == "__main__":
    main(prog_name="ct-sr")  # pragma: no cover
