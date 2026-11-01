"""Resolve trusted release metadata without interpolating input into shell code."""
import json
import os
import re

TAG = re.compile(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")


def release_plan(event, ref, run_number, requested=""):
    if not str(run_number).isdigit() or not 0 < int(run_number) < 2100000000:
        raise ValueError("Invalid Android build number")
    tag = ref.removeprefix("refs/tags/") if event == "push" and ref.startswith("refs/tags/") else requested or f"v0.6.{int(run_number)}"
    if len(tag) > 64 or not TAG.fullmatch(tag):
        raise ValueError("Use a version such as v0.6.10 or v0.7.0-beta.1")
    return {"tag": tag, "version": tag[1:], "prerelease": str("-" in tag).lower()}


if __name__ == "__main__":
    plan = release_plan(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"], os.environ["GITHUB_RUN_NUMBER"], os.environ.get("MEDTERM_RELEASE_VERSION", ""))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for key, value in plan.items():
                output.write(f"{key}={value}\n")
    print(json.dumps(plan))
