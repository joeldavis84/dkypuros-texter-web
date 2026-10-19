#!/usr/bin/python3.11

"""Render the mounted UE template using the init container's environment."""

import os
from pathlib import Path
from string import Template
import sys


def main():

    names = ("imsi", "imei", "key", "opc", "mcc", "mnc", "templatePath", "outputPath")
    missing = [name for name in names if not os.environ.get(name)]

    if missing:

        print("Missing required environment variables: " + ", ".join(missing), file=sys.stderr)
        return 1

    try:

        template = Path(os.environ["templatePath"]).read_text(encoding="utf-8")
        values = {name: os.environ[name] for name in names[:6]}
        rendered = Template(template).substitute(values)

        output = Path(os.environ["outputPath"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")

    except (OSError, ValueError, KeyError):

          ## Do not expose the template or subscriber credentials in pod logs.
        print("Unable to render UE config; check paths and template placeholders.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
